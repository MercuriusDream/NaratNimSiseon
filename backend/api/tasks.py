import requests
import pdfplumber
from celery import shared_task
from django.conf import settings
from .models import Session, Bill, Speaker, Statement, VotingRecord, Party, Category, Subcategory, BillCategoryMapping, BillSubcategoryMapping
from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import RequestException
import logging
from celery.schedules import crontab
from datetime import datetime, timedelta, time as dt_time
import json
import time
from pathlib import Path
import threading
from collections import deque
import re

# Import the new Gemini SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False
    logger.warning("google.genai not available, falling back to google.generativeai")
    try:
        import google.generativeai as genai_legacy
        GENAI_LEGACY_AVAILABLE = True
    except ImportError:
        genai_legacy = None
        GENAI_LEGACY_AVAILABLE = False

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """Enhanced rate limiter for Gemini API calls to respect token limits."""

    def __init__(
        self,
        max_tokens_per_minute=250000,
        max_requests_per_minute=60,  # Standard Gemini 1.5 Flash limit
        max_tokens_per_day=2000000):  # Realistic free tier daily limit
        """
        Initialize rate limiter with updated limits.
        """
        self.max_tokens_per_minute = max_tokens_per_minute
        self.max_requests_per_minute = max_requests_per_minute
        self.max_tokens_per_day = max_tokens_per_day
        self.token_usage = deque()
        self.request_times = deque()
        self.daily_token_usage = deque()
        self.lock = threading.Lock()
        self.consecutive_errors = 0
        self.last_error_time = None

    def _cleanup_old_records(self):
        """Remove records older than their respective time windows"""
        now = datetime.now()
        minute_cutoff = now - timedelta(minutes=1)
        day_cutoff = now - timedelta(days=1)

        # Clean minute-based records
        while self.token_usage and self.token_usage[0][0] < minute_cutoff:
            self.token_usage.popleft()

        while self.request_times and self.request_times[0] < minute_cutoff:
            self.request_times.popleft()

        # Clean daily records
        while self.daily_token_usage and self.daily_token_usage[0][
                0] < day_cutoff:
            self.daily_token_usage.popleft()

    def _calculate_backoff_time(self):
        """Calculate exponential backoff time based on consecutive errors"""
        if self.consecutive_errors == 0:
            return 0

        # Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 60s
        backoff = min(60, 2**(self.consecutive_errors - 1))
        return backoff

    def can_make_request(self, estimated_tokens=1000):
        """Check if we can make a request without hitting limits"""
        with self.lock:
            self._cleanup_old_records()

            # Check if we're in backoff period due to errors
            if self.last_error_time and self.consecutive_errors > 0:
                time_since_error = (datetime.now() -
                                    self.last_error_time).total_seconds()
                required_backoff = self._calculate_backoff_time()
                if time_since_error < required_backoff:
                    return False, f"In backoff period ({required_backoff - time_since_error:.1f}s remaining)"

            # Check request count limit (per minute)
            if len(self.request_times) >= self.max_requests_per_minute:
                return False, f"Request limit reached ({len(self.request_times)}/{self.max_requests_per_minute} per minute)"

            # Check token limit (per minute)
            current_tokens = sum(count for _, count in self.token_usage)
            if current_tokens + estimated_tokens > self.max_tokens_per_minute:
                return False, f"Token limit would be exceeded ({current_tokens} + {estimated_tokens} > {self.max_tokens_per_minute} per minute)"

            # Check daily token limit
            daily_tokens = sum(count for _, count in self.daily_token_usage)
            if daily_tokens + estimated_tokens > self.max_tokens_per_day:
                return False, f"Daily token limit would be exceeded ({daily_tokens} + {estimated_tokens} > {self.max_tokens_per_day})"

            return True, "OK"

    def record_request(self, actual_tokens=1000, success=True):
        """Record a completed request"""
        with self.lock:
            now = datetime.now()
            self.request_times.append(now)
            self.token_usage.append((now, actual_tokens))
            self.daily_token_usage.append((now, actual_tokens))

            # Update error tracking
            if success:
                self.consecutive_errors = 0
                self.last_error_time = None
            else:
                self.consecutive_errors += 1
                self.last_error_time = now
                logger.warning(
                    f"API error recorded. Consecutive errors: {self.consecutive_errors}"
                )

            self._cleanup_old_records()

    def record_error(self, error_type="unknown"):
        """Record an API error for backoff calculation"""
        with self.lock:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            backoff_time = self._calculate_backoff_time()
            logger.warning(
                f"API error ({error_type}). Consecutive errors: {self.consecutive_errors}, backoff: {backoff_time}s"
            )

    def wait_if_needed(self, estimated_tokens=1000, max_wait_time=120):
        """Wait if necessary to respect rate limits with enhanced backoff"""
        wait_start = time.time()

        while time.time() - wait_start < max_wait_time:
            can_proceed, reason = self.can_make_request(estimated_tokens)
            if can_proceed:
                return True

            # Determine wait time based on reason
            if "backoff" in reason.lower():
                # Extract remaining backoff time from reason
                try:
                    remaining_time = float(reason.split('(')[1].split('s')[0])
                    wait_time = min(10, max(1, remaining_time))
                except:
                    wait_time = 5
            elif "daily" in reason.lower():
                logger.error(f"Daily rate limit exceeded: {reason}")
                return False  # Don't wait for daily limits
            else:
                wait_time = 10  # Default wait time for other limits

            logger.info(
                f"Rate limit hit: {reason}. Waiting {wait_time} seconds...")
            time.sleep(wait_time)

        logger.warning(
            f"Max wait time ({max_wait_time}s) exceeded for rate limiting")
        return False

    def get_usage_stats(self):
        """Get current usage statistics"""
        with self.lock:
            self._cleanup_old_records()

            current_requests = len(self.request_times)
            current_tokens = sum(count for _, count in self.token_usage)
            daily_tokens = sum(count for _, count in self.daily_token_usage)

            return {
                "requests_per_minute":
                f"{current_requests}/{self.max_requests_per_minute}",
                "tokens_per_minute":
                f"{current_tokens}/{self.max_tokens_per_minute}",
                "daily_tokens":
                f"{daily_tokens}/{self.max_tokens_per_day}",
                "consecutive_errors":
                self.consecutive_errors,
                "backoff_time":
                self._calculate_backoff_time()
                if self.consecutive_errors > 0 else 0
            }


# Global instances
gemini_rate_limiter = GeminiRateLimiter()
client = None  # Will be initialized by initialize_gemini()
model = None  # Deprecated - use client instead


def initialize_gemini():
    """Initializes the Gemini client using new google.genai or fallback to legacy."""
    global client
    
    # Skip if already initialized
    if client is not None:
        return True
        
    try:
        if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
            if GENAI_AVAILABLE:
                # Use the new genai.Client structure
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("✅ Gemini API client initialized successfully with google.genai")
                
                # Test the client with a simple call
                test_response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=["Hello"]
                )
                logger.info(f"✅ Gemini API test successful. Response: {test_response.text[:50]}...")
                return True
            elif GENAI_LEGACY_AVAILABLE:
                # Fallback to legacy google.generativeai
                genai_legacy.configure(api_key=settings.GEMINI_API_KEY)
                client = genai_legacy
                logger.info("✅ Gemini API configured with legacy google.generativeai")
                return True
            else:
                logger.warning("⚠️ Neither google.genai nor google.generativeai available.")
                client = None
                return False
        else:
            logger.warning("⚠️ GEMINI_API_KEY not found. LLM features will be disabled.")
            client = None
            return False
    except Exception as e:
        logger.error(f"❌ Error configuring Gemini API: {e}. LLM features will be disabled.")
        client = None
        return False


# Initialize on module load (only once)
initialize_gemini()


def _call_gemini_api(prompt: str,
                     model_name: str = "gemini-2.0-flash",
                     system_instruction: str = None,
                     response_mime_type: str = "text/plain",
                     max_retries: int = 2,
                     timeout: int = 180) -> str | dict | None:
    """
    A unified, robust function to call the Gemini API using new google.genai structure.
    Handles rate limiting, error handling, retries, and JSON parsing.
    """
    global client
    if not client:
        logger.error("Gemini client not initialized. Cannot make API call.")
        return None

    # Estimate tokens for rate limiting (very rough but better than nothing)
    estimated_tokens = len(prompt) // 2
    if not gemini_rate_limiter.wait_if_needed(estimated_tokens):
        logger.error("Aborting API call due to rate limiting timeout.")
        return None

    for attempt in range(max_retries + 1):
        try:
            if GENAI_AVAILABLE and hasattr(client, 'models'):
                # Use new google.genai structure
                config = types.GenerateContentConfig(response_mime_type=response_mime_type)
                
                # Add system instruction if provided
                if system_instruction:
                    config.system_instruction = system_instruction

                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt],
                    config=config
                )
                response_text = response.text
                
            elif GENAI_LEGACY_AVAILABLE:
                # Use legacy google.generativeai
                model = client.GenerativeModel(model_name)
                if system_instruction:
                    model = client.GenerativeModel(model_name, system_instruction=system_instruction)
                
                response = model.generate_content(prompt)
                response_text = response.text
            else:
                logger.error("No available Gemini API client")
                return None

            # Record successful request
            gemini_rate_limiter.record_request(estimated_tokens, success=True)

            # Parse response based on mime type
            if response_mime_type == "application/json":
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    return None
            return response_text

        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}"
            )
            gemini_rate_limiter.record_request(estimated_tokens, success=False)

            if attempt < max_retries:
                # Exponential backoff
                backoff = min(60, 2**attempt)
                logger.info(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
                continue

            return None


def log_rate_limit_status():
    """Log current rate limit status for monitoring"""
    stats = gemini_rate_limiter.get_usage_stats()
    logger.info("Rate limit status: %s", stats)
    logger.info(f"📊 Rate Limit Status: {stats}")
    return stats


def with_db_retry(func, max_retries=3):
    """Wrapper to retry database operations with connection management for serverless databases"""

    def wrapper(*args, **kwargs):
        from django.db import connection
        from django.db.utils import OperationalError, InterfaceError
        import psycopg2

        for attempt in range(max_retries):
            try:
                # Close any stale connections before starting
                if connection.connection and hasattr(
                        connection.connection,
                        'closed') and connection.connection.closed:
                    connection.close()

                # Ensure fresh connection
                connection.ensure_connection()
                return func(*args, **kwargs)

            except (OperationalError, InterfaceError,
                    psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                error_msg = str(e).lower()
                is_connection_error = any(phrase in error_msg for phrase in [
                    'connection already closed',
                    'server closed the connection',
                    'ssl connection has been closed unexpectedly',
                    'ssl connection has been closed', 'connection lost',
                    'connection broken', 'server has gone away',
                    'connection timeout', 'connection was lost',
                    'database connection was lost',
                    'server closed the connection unexpectedly'
                ])

                if is_connection_error:
                    logger.warning(
                        f"Database connection issue on attempt {attempt + 1}/{max_retries}: {e}"
                    )
                    if attempt < max_retries - 1:
                        # Force close the connection and wait before retry
                        try:
                            connection.close()
                        except:
                            pass  # Ignore errors when closing

                        # Exponential backoff: 1s, 2s, 4s
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for database operation"
                        )
                        raise e
                else:
                    # Non-connection database error, don't retry
                    logger.error(
                        f"Non-connection database error (not retrying): {e}")
                    raise e

            except Exception as e:
                # For non-database errors, don't retry
                logger.error(
                    f"Non-database error in with_db_retry (not retrying): {e}")
                raise e

        return None

    return wrapper


# Configure logger to actually show output if not already configured by Django
if not logger.handlers or not any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers):
    import sys
    logger.setLevel(
        logging.DEBUG)  # Set to DEBUG for development, INFO for production
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)  # Or match logger.level
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # print(
    #     f"🐛 IMMEDIATE DEBUG: Logger reconfigured with handlers: {logger.handlers}"
    # )

# Configuration flags
ENABLE_VOTING_DATA_COLLECTION = getattr(settings,
                                        'ENABLE_VOTING_DATA_COLLECTION', False)
initialize_gemini()


def reinitialize_gemini():
    """Reinitialize Gemini if it failed initially"""
    global client
    if not client:
        logger.info("🔄 Attempting to reinitialize Gemini API...")
        success = initialize_gemini()
        return success
    return True


def check_gemini_api_status():
    """
    Check Gemini API status by sending a minimal prompt and returning the response or error.
    Returns a tuple: (status: str, info: str)
    """
    global client

    if client is None:
        return "error", "Gemini API client not initialized"

    try:
        # Test with a minimal prompt using new structure
        response = client.models.generate_content(model="gemini-2.0-flash",
                                                  contents=["Hello"])
        return "success", f"API is responding. Response: {response.text[:50]}..."
    except Exception as e:
        return "error", f"API Error: {str(e)}"


# Check if Celery/Redis is available
def is_celery_available():
    """Check if Celery/Redis is available for async tasks"""
    from kombu.exceptions import OperationalError
    from celery import current_app
    try:
        # Check if the app is configured and has a broker
        if not current_app.conf.broker_url:
            logger.info("Celery broker_url not configured.")
            return False
        current_app.control.inspect().ping()  # More reliable check
        return True
    except (ImportError, OperationalError, OSError, ConnectionError,
            AttributeError) as e:
        logger.warning(
            f"Celery not available or broker connection failed: {e}")
        return False


# Decorator to handle both sync and async execution
def celery_or_sync(func):
    """Decorator that runs function sync if Celery is not available"""

    def wrapper(*args, **kwargs):
        if is_celery_available():
            logger.info(
                f"🔄 Running {func.__name__} asynchronously with Celery")
            # For bound tasks, Celery handles 'self' automatically when calling .delay()
            return func.delay(*args, **kwargs)
        else:
            logger.info(
                f"🔄 Running {func.__name__} synchronously (Celery not available)"
            )
            # Remove 'self' if it's the first arg and the function is a bound task
            # This is tricky; usually, for bound tasks, direct call should not include 'self' unless it's a method
            # If func is a @shared_task(bind=True), its __wrapped__ won't expect 'self' directly
            # A direct call to a Celery task function `func(*args, **kwargs)` should work as expected.
            if hasattr(func, '__wrapped__') and 'bind' in func.__dict__.get(
                    '__header__', {}):
                # Call the original function without 'self' if it's a bound task being run synchronously
                return func.__wrapped__(None, *args,
                                        **kwargs)  # Pass None for self
            return func(*args, **kwargs)

    return wrapper


# Removed duplicate imports for shared_task and logging if they were here

# from .utils import DataCollector # Marked as unused, remove if not needed
# from .llm_analyzer import LLMPolicyAnalyzer # Marked as unused, remove if not needed


def format_conf_id(conf_id):
    """Format CONF_ID with zero-filled 6 digits (no N prefix)."""
    # Remove any existing 'N' prefix and convert to string
    clean_id = str(conf_id).replace('N', '').strip()
    # Zero-fill to 6 digits without N prefix
    return clean_id.zfill(6)


def fetch_speaker_details(speaker_name):
    """Fetch speaker details from ALLNAMEMBER API"""
    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                "ASSEMBLY_API_KEY not configured for fetch_speaker_details.")
            return None

        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "NAAS_NM": speaker_name,
            "Type": "json",
            "pSize":
            5  # Fetch a few in case of name ambiguity, pick the best match
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        logger.debug(
            f"🐛 DEBUG: ALLNAMEMBER API response for {speaker_name}: {json.dumps(data, indent=2, ensure_ascii=False)}"
        )

        member_data_list = []
        if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
            member_data_list = data['ALLNAMEMBER'][1].get('row', [])

        if not member_data_list:
            logger.warning(
                f"⚠️ No member data found for: {speaker_name} via ALLNAMEMBER API."
            )
            return None

        # Logic to pick the best match if multiple results (e.g., current term, exact name match)
        member_data = member_data_list[0]  # Simplistic: take the first for now

        # Use update_or_create for robustness
        speaker, created = Speaker.objects.update_or_create(
            naas_cd=member_data.get('NAAS_CD'),  # Assuming NAAS_CD is unique
            defaults={
                'naas_nm': member_data.get('NAAS_NM', speaker_name),
                'naas_ch_nm': member_data.get('NAAS_CH_NM', ''),
                'plpt_nm': member_data.get('PLPT_NM', '정당정보없음'),
                'elecd_nm': member_data.get('ELECD_NM', ''),
                'elecd_div_nm': member_data.get('ELECD_DIV_NM', ''),
                'cmit_nm': member_data.get('CMIT_NM', ''),
                'blng_cmit_nm': member_data.get('BLNG_CMIT_NM', ''),
                'rlct_div_nm': member_data.get('RLCT_DIV_NM', ''),
                'gtelt_eraco': member_data.get('GTELT_ERACO',
                                               ''),  # Era might be important
                'ntr_div': member_data.get('NTR_DIV', ''),
                'naas_pic': member_data.get('NAAS_PIC', '')
            })

        status_msg = "Created" if created else "Updated"
        logger.info(
            f"✅ {status_msg} speaker details for: {speaker_name} (ID: {speaker.naas_cd})"
        )
        return speaker

    except requests.exceptions.RequestException as e:
        logger.error(
            f"❌ Network error fetching speaker details for {speaker_name}: {e}"
        )
    except json.JSONDecodeError as e:
        logger.error(
            f"❌ JSON parsing error for speaker details {speaker_name}: {e}")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching speaker details for {speaker_name}: {e}"
        )
    return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_party_membership_data(self=None, force=False, debug=False):
    """Fetch party membership data from Assembly API."""
    logger.info(
        f"🏛️ Fetching party membership data (force={force}, debug={debug})")

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                "ASSEMBLY_API_KEY not configured for party membership data.")
            return

        # Use ALLNAMEMBER API to get all assembly members
        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"

        all_members = []
        current_page = 1
        page_size = 300
        max_pages = 10

        while current_page <= max_pages:
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": current_page,
                "pSize": page_size
            }

            logger.info(
                f"Fetching page {current_page} of party membership data")

            if debug:
                logger.debug(
                    f"🐛 DEBUG: Would fetch page {current_page} (skipping actual call)"
                )
                break

            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            members_on_page = []
            if data and 'ALLNAMEMBER' in data and isinstance(
                    data['ALLNAMEMBER'], list):
                if len(data['ALLNAMEMBER']) > 1 and isinstance(
                        data['ALLNAMEMBER'][1], dict):
                    members_on_page = data['ALLNAMEMBER'][1].get('row', [])
                elif len(data['ALLNAMEMBER']) > 0 and isinstance(
                        data['ALLNAMEMBER'][0], dict):
                    head_info = data['ALLNAMEMBER'][0].get('head')
                    if head_info and head_info[0].get('RESULT', {}).get(
                            'CODE', '').startswith("INFO-200"):
                        logger.info(
                            "API indicates no more member data available")
                        break
                    elif 'row' in data['ALLNAMEMBER'][0]:
                        members_on_page = data['ALLNAMEMBER'][0].get('row', [])

            if not members_on_page:
                logger.info(
                    f"No members found on page {current_page}, ending pagination"
                )
                break

            all_members.extend(members_on_page)
            logger.info(
                f"Fetched {len(members_on_page)} members from page {current_page}. Total: {len(all_members)}"
            )

            if len(members_on_page) < page_size:
                logger.info(
                    "Fetched less members than page size, assuming last page")
                break

            current_page += 1
            time.sleep(1)  # Be respectful to API

        if not all_members:
            logger.info("No party membership data found")
            return

        logger.info(f"✅ Found {len(all_members)} total members")

        # Process and update Speaker records with party information
        processed_count = 0
        for member_data in all_members:
            try:
                member_name = member_data.get('NAAS_NM', '').strip()
                party_name = member_data.get('PLPT_NM', '').strip()

                if not member_name:
                    continue

                # Update or create Speaker with party information
                speaker, created = Speaker.objects.update_or_create(
                    naas_cd=member_data.get('NAAS_CD', f'TEMP_{member_name}'),
                    defaults={
                        'naas_nm': member_name,
                        'naas_ch_nm': member_data.get('NAAS_CH_NM', ''),
                        'plpt_nm': party_name or '정당정보없음',
                        'elecd_nm': member_data.get('ELECD_NM', ''),
                        'elecd_div_nm': member_data.get('ELECD_DIV_NM', ''),
                        'cmit_nm': member_data.get('CMIT_NM', ''),
                        'blng_cmit_nm': member_data.get('BLNG_CMIT_NM', ''),
                        'rlct_div_nm': member_data.get('RLCT_DIV_NM', ''),
                        'gtelt_eraco': member_data.get('GTELT_ERACO', ''),
                        'ntr_div': member_data.get('NTR_DIV', ''),
                        'naas_pic': member_data.get('NAAS_PIC', '')
                    })

                # Create or update Party record
                if party_name and party_name != '정당정보없음':
                    party, party_created = Party.objects.get_or_create(
                        name=party_name,
                        defaults={
                            'description': f'정당 - {party_name}',
                            'assembly_era': 22
                        })

                    # Update speaker's current party
                    if not speaker.current_party:
                        speaker.current_party = party
                        speaker.save()

                processed_count += 1

                if processed_count % 50 == 0:
                    logger.info(f"Processed {processed_count} members...")

            except Exception as e:
                logger.error(f"Error processing member data: {e}")
                continue

        logger.info(f"🎉 Processed {processed_count} party membership records")

    except RequestException as re_exc:
        logger.error(f"Request error fetching party membership data: {re_exc}")
        if self:
            try:
                self.retry(exc=re_exc)
            except MaxRetriesExceededError:
                logger.error("Max retries for party membership data fetch")
    except Exception as e:
        logger.error(f"❌ Unexpected error fetching party membership data: {e}")
        logger.exception("Full traceback for party membership error:")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    "Max retries after unexpected error for party membership")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_additional_data_nepjpxkkabqiqpbvk(self=None,
                                            force=False,
                                            debug=False):
    """Fetch additional data using nepjpxkkabqiqpbvk API endpoint."""
    api_endpoint_name = "nepjpxkkabqiqpbvk"  # Store endpoint name for logging
    logger.info(
        f"🔍 Fetching additional data from {api_endpoint_name} API (force={force}, debug={debug})"
    )

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                f"ASSEMBLY_API_KEY not configured for {api_endpoint_name}.")
            return

        url = f"https://open.assembly.go.kr/portal/openapi/{api_endpoint_name}"

        all_items = []
        current_page = 1
        page_size = 100  # Adjust as per API limit, usually 100 or 1000
        max_pages = 10  # Safety break for pagination

        while current_page <= max_pages:
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": current_page,
                "pSize": page_size
                # Add other API-specific parameters if needed (e.g., date range, DAE_NUM)
            }
            logger.info(
                f"Fetching page {current_page} from {api_endpoint_name} with params: {params}"
            )
            if debug:
                logger.debug(
                    f"🐛 DEBUG: Would fetch page {current_page} from {api_endpoint_name} (skipping actual call in debug mode)."
                )
                # Provide mock data for testing in debug mode
                items_on_page = [{
                    "MOCK_FIELD": f"Mock item {current_page}-{i}"
                } for i in range(3)] if current_page == 1 else []
            else:
                response = requests.get(url, params=params, timeout=60)
                response.raise_for_status()
                data = response.json()

                items_on_page = []
                if data and api_endpoint_name in data and isinstance(
                        data[api_endpoint_name], list):
                    if len(data[api_endpoint_name]) > 1 and isinstance(
                            data[api_endpoint_name][1], dict):
                        items_on_page = data[api_endpoint_name][1].get(
                            'row', [])
                    elif len(data[api_endpoint_name]) > 0 and isinstance(
                            data[api_endpoint_name][0], dict):
                        head_info = data[api_endpoint_name][0].get('head')
                        if head_info and head_info[0].get('RESULT', {}).get(
                                'CODE', '').startswith("INFO-200"):
                            logger.info(
                                f"API result for {api_endpoint_name} (page {current_page}) indicates no more data."
                            )
                            break
                        elif 'row' in data[api_endpoint_name][0]:
                            items_on_page = data[api_endpoint_name][0].get(
                                'row', [])

            if not items_on_page:
                logger.info(
                    f"No items found on page {current_page} for {api_endpoint_name}. Ending pagination."
                )
                break  # End pagination if no items or API indicates end of data

            all_items.extend(items_on_page)
            logger.info(
                f"Fetched {len(items_on_page)} items from page {current_page}. Total so far: {len(all_items)}."
            )

            # Check if this was the last page (e.g., if less items than pSize returned)
            if len(items_on_page) < page_size:
                logger.info(
                    "Fetched less items than page size, assuming last page.")
                break

            current_page += 1
            if not debug: time.sleep(1)  # Be respectful

        if not all_items:
            logger.info(
                f"ℹ️  No data items found from {api_endpoint_name} API after checking pages."
            )
            return

        logger.info(
            f"✅ Found a total of {len(all_items)} items from {api_endpoint_name} API."
        )

        processed_count = 0
        # Placeholder: Actual processing logic depends on the data from 'nepjpxkkabqiqpbvk'
        # Example: if items are bill proposals, committee activities, member updates, etc.
        for item in all_items:
            try:
                # EXAMPLE: item_id = item.get('UNIQUE_ID_FIELD')
                # if not item_id: continue
                # YourModel.objects.update_or_create(api_id=item_id, defaults={...})
                logger.debug(
                    f"Processing item (placeholder): {str(item)[:200]}...")
                processed_count += 1
            except Exception as e_item:
                logger.error(
                    f"❌ Error processing item from {api_endpoint_name}: {e_item}. Item: {str(item)[:100]}"
                )
                continue

        logger.info(
            f"🎉 Processed {processed_count} items from {api_endpoint_name} API."
        )

    except RequestException as re_exc:
        logger.error(
            f"Request error fetching from {api_endpoint_name} API: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for {api_endpoint_name} fetch.")
    except json.JSONDecodeError as json_e:
        logger.error(
            f"JSON decode error from {api_endpoint_name} API: {json_e}")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching/processing from {api_endpoint_name} API: {e}"
        )
        logger.exception(f"Full traceback for {api_endpoint_name} error:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected error for {api_endpoint_name}.")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_continuous_sessions(
        self,  # Celery provides 'self'
        force=False,
        debug=False,
        start_date=None):
    """Fetch sessions starting from a specific date or continue from last session."""
    try:
        logger.info(
            f"🔍 Starting continuous session fetch (force={force}, debug={debug}, start_date={start_date})"
        )

        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("❌ ASSEMBLY_API_KEY not configured")
            raise ValueError("ASSEMBLY_API_KEY not configured")

        url = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
            except ValueError:
                logger.error(
                    f"Invalid start_date format: {start_date}. Expected ISO format (YYYY-MM-DD)."
                )
                return  # Or raise error
            logger.info(
                f"📅 Continuing from date: {start_datetime.strftime('%Y-%m')}")
        else:
            start_datetime = datetime.now()
            logger.info(
                f"📅 Starting from current date: {start_datetime.strftime('%Y-%m')}"
            )

        current_date = start_datetime
        sessions_found_in_period = False
        DAE_NUM_TARGET = "22"  # Consider making this configurable

        # Go back up to 36 months, or until a configurable DAE_NUM boundary is hit
        for months_back in range(0, 36):
            target_date = current_date - timedelta(
                days=months_back * 30.44)  # Approximate month step back
            conf_date_str = target_date.strftime('%Y-%m')

            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "DAE_NUM": DAE_NUM_TARGET,
                "CONF_DATE": conf_date_str,
                "pSize": 500  # Fetch more per request if API allows
            }

            logger.info(f"📅 Fetching sessions for: {conf_date_str}")
            if debug:
                logger.debug(f"🐛 DEBUG: API URL: {url}, Params: {params}")

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if debug:
                    logger.debug(
                        f"🐛 DEBUG: API Response status for {conf_date_str}: {response.status_code}"
                    )
                    # logger.debug(f"🐛 DEBUG: API Response data: {json.dumps(data, indent=2, ensure_ascii=False)}")

                sessions_data = extract_sessions_from_response(data,
                                                               debug=debug)

                if sessions_data:
                    sessions_found_in_period = True
                    logger.info(
                        f"✅ Found {len(sessions_data)} session items for {conf_date_str}"
                    )
                    process_sessions_data(sessions_data,
                                          force=force,
                                          debug=debug)
                    if not debug: time.sleep(1)  # Be respectful to API
                else:
                    logger.info(f"❌ No sessions found for {conf_date_str}")
                    if months_back > 6 and not sessions_found_in_period:
                        logger.info(
                            "🛑 No sessions found in recent ~6 months of search, stopping."
                        )
                        break
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"⚠️ Request error fetching {conf_date_str}: {e}")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ JSON parsing error for {conf_date_str}: {e}")
            except Exception as e:  # Catch other potential errors per iteration
                logger.warning(
                    f"⚠️ Unexpected error fetching/processing {conf_date_str}: {e}"
                )
                if debug:
                    logger.exception("Full traceback for error during loop:")
            continue

        if not debug and sessions_found_in_period:  # Only call if some sessions were processed
            logger.info("🔄 Triggering additional data collection...")
            if is_celery_available():
                fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force,
                                                              debug=debug)
            else:
                fetch_additional_data_nepjpxkkabqiqpbvk(force=force,
                                                        debug=debug)

        if sessions_found_in_period:
            logger.info("🎉 Continuous session fetch attempt completed.")
        else:
            logger.info(
                "ℹ️ No new sessions found during this continuous fetch period."
            )

    except ValueError as ve:  # Catch config errors early
        logger.error(f"Configuration error: {ve}")
        # Do not retry config errors usually
    except RequestException as re_exc:
        logger.error(f"A request exception occurred: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded for fetch_continuous_sessions.")
    except Exception as e:
        logger.error(f"❌ Critical error in fetch_continuous_sessions: {e}")
        logger.exception("Full traceback for critical error:")
        try:  # Try to retry for unexpected critical errors too
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded after critical error.")
        # Optionally re-raise if you want the task to be marked as FAILED in Celery Flower/logs
        # raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_latest_sessions(self,
                          force=False,
                          debug=False):  # Celery provides 'self'
    """Fetch latest assembly sessions from the API."""
    logger.info(f"🔍 Starting session fetch (force={force}, debug={debug})")

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("❌ ASSEMBLY_API_KEY not configured or empty.")
            raise ValueError(
                "ASSEMBLY_API_KEY not configured")  # Stop if key missing

        url = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"
        DAE_NUM_TARGET = "22"  # Make configurable if needed

        if not force:
            logger.info(
                "📅 Fetching sessions for current and previous month (non-force mode)."
            )
            dates_to_check = [
                datetime.now().strftime('%Y-%m'),
                (datetime.now() - timedelta(days=30)).strftime('%Y-%m')
            ]
            unique_conf_dates = sorted(list(set(dates_to_check)), reverse=True)

            for conf_date_str in unique_conf_dates:
                params = {
                    "KEY": settings.ASSEMBLY_API_KEY,
                    "Type": "json",
                    "DAE_NUM": DAE_NUM_TARGET,
                    "CONF_DATE": conf_date_str,
                    "pSize": 500  # Fetch more per request if API allows
                }
                logger.info(f"📅 Fetching sessions for: {conf_date_str}")
                if debug:
                    logger.debug(f"🐛 DEBUG: API URL: {url}, Params: {params}")

                try:
                    response = requests.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    if debug:
                        logger.debug(
                            f"🐛 DEBUG: API Response status for {conf_date_str}: {response.status_code}"
                        )
                        # logger.debug(f"🐛 DEBUG: Full API response: {json.dumps(data, indent=2, ensure_ascii=False)}")

                    sessions_data = extract_sessions_from_response(data,
                                                                   debug=debug)
                    if sessions_data:
                        process_sessions_data(
                            sessions_data, force=False,
                            debug=debug)  # force is False here
                    else:
                        logger.info(
                            f"No sessions data found for {conf_date_str} in non-force mode."
                        )
                    if not debug: time.sleep(1)
                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"⚠️ Request error fetching {conf_date_str} (non-force): {e}"
                    )
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"⚠️ JSON parsing error for {conf_date_str} (non-force): {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Error processing {conf_date_str} (non-force): {e}"
                    )
        else:  # Force mode
            logger.info(
                "🔄 Force mode: Fetching sessions month by month for up to 24 months."
            )
            current_loop_date = datetime.now()
            for months_back in range(0, 24):
                target_date = current_loop_date - timedelta(days=months_back *
                                                            30.44)
                conf_date_str = target_date.strftime('%Y-%m')
                params = {
                    "KEY": settings.ASSEMBLY_API_KEY,
                    "Type": "json",
                    "DAE_NUM": DAE_NUM_TARGET,
                    "CONF_DATE": conf_date_str,
                    "pSize": 500
                }
                logger.info(
                    f"📅 Fetching sessions for: {conf_date_str} (force mode)")
                if debug:
                    logger.debug(
                        f"🐛 DEBUG: API URL: {url}, Params for {conf_date_str}: {params}"
                    )

                try:
                    response = requests.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    if debug:
                        logger.debug(
                            f"🐛 DEBUG: API Response status for {conf_date_str}: {response.status_code}"
                        )
                        # logger.debug(f"🐛 DEBUG: Full API response for {conf_date_str}: {json.dumps(data, indent=2, ensure_ascii=False)}")

                    sessions_data = extract_sessions_from_response(data,
                                                                   debug=debug)
                    if sessions_data:
                        process_sessions_data(
                            sessions_data, force=True,
                            debug=debug)  # force is True here
                    else:
                        logger.info(
                            f"❌ No sessions found for {conf_date_str} in force mode. Might be end of data for DAE_NUM {DAE_NUM_TARGET}."
                        )
                        # Optionally break if no sessions found for a few consecutive months
                    if not debug: time.sleep(1)
                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"⚠️ Request error fetching {conf_date_str} (force): {e}"
                    )
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"⚠️ JSON parsing error for {conf_date_str} (force): {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Error processing {conf_date_str} (force): {e}")
                    if debug:
                        logger.debug(
                            f"🐛 DEBUG: Full error: {type(e).__name__}: {e}")
                continue

        if not debug:  # Consider if this should run even if no sessions were found/updated
            logger.info(
                "🔄 Triggering additional data collection after session fetch.")
            if is_celery_available():
                fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force,
                                                              debug=debug)
            else:
                fetch_additional_data_nepjpxkkabqiqpbvk(force=force,
                                                        debug=debug)

        logger.info("🎉 Session fetch attempt completed.")

    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
    except RequestException as re_exc:
        logger.error(f"A request exception occurred: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded for fetch_latest_sessions.")
    except Exception as e:
        logger.error(f"❌ Critical error in fetch_latest_sessions: {e}")
        logger.exception("Full traceback for critical error:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded after critical error.")
        # raise # Optionally re-raise


def extract_sessions_from_response(data, debug=False):
    """Extract sessions data from API response for nzbyfwhwaoanttzje"""
    sessions_data_list = []
    api_key_name = 'nzbyfwhwaoanttzje'  # Specific to this API endpoint

    if data and api_key_name in data and isinstance(data[api_key_name], list):
        if len(data[api_key_name]) > 1 and isinstance(data[api_key_name][1],
                                                      dict):
            sessions_data_list = data[api_key_name][1].get('row', [])
            if debug:
                logger.debug(
                    f"Extracted data from data['{api_key_name}'][1]['row']")
        elif len(data[api_key_name]) > 0 and isinstance(
                data[api_key_name][0], dict):
            # Check head for result code before assuming it's data
            head_info = data[api_key_name][0].get('head')
            if head_info:
                result_code_info = head_info[0].get('RESULT', {}).get(
                    'CODE', '').startswith("INFO-200")
                if result_code_info.startswith(
                        "INFO-") or result_code_info.startswith(
                            "ERROR-"):  # Assuming "INFO-200" is no data
                    logger.info(
                        f"API result indicates no data or error: {result_code_info} in head."
                    )
                    # Check if 'row' exists in the first element anyway as some APIs are inconsistent
                    if 'row' in data[api_key_name][0]:
                        sessions_data_list = data[api_key_name][0].get(
                            'row', [])

        if not sessions_data_list and debug:  # if still no data and debug
            logger.debug(
                f"No 'row' found in expected paths data['{api_key_name}'][1] or data['{api_key_name}'][0]. API structure might have changed or no data."
            )
            # logger.debug(f"Full response for {api_key_name} if empty: {data[api_key_name]}")

    elif data and 'row' in data and isinstance(
            data['row'], list):  # Fallback for simpler structure
        sessions_data_list = data['row']
        if debug: logger.debug("Extracted data from data['row'] (fallback).")
    else:
        if debug:
            logger.debug(
                f"Could not find session data in expected structures. Keys: {list(data.keys()) if data else 'Empty data'}"
            )

    if debug and sessions_data_list:
        logger.debug(
            f"Extracted {len(sessions_data_list)} session items. Sample: {sessions_data_list[0] if sessions_data_list else 'None'}"
        )
    elif not sessions_data_list:
        logger.info("No session items extracted from the API response.")

    return sessions_data_list


# In tasks.py, replace the existing process_sessions_data function


def process_sessions_data(sessions_data, force=False, debug=False):
    """Process the sessions data and create/update session objects.
    This function now directly orchestrates the fetching of bills and processing of PDFs for each session."""
    if not sessions_data:
        logger.info("No sessions data provided to process.")
        return

    from django.db import connection

    @with_db_retry
    def _process_session_item(session_defaults, confer_num):
        return Session.objects.update_or_create(conf_id=confer_num,
                                                defaults=session_defaults)

    sessions_by_confer_num = {}
    for item_data in sessions_data:
        confer_num = item_data.get('CONFER_NUM')
        if not confer_num:
            continue
        if confer_num not in sessions_by_confer_num:
            sessions_by_confer_num[confer_num] = []
        sessions_by_confer_num[confer_num].append(item_data)

    logger.info(
        f"Processing {len(sessions_by_confer_num)} unique sessions from {len(sessions_data)} API items."
    )
    created_count = 0
    updated_count = 0

    for confer_num, items_for_session in sessions_by_confer_num.items():
        connection.ensure_connection()
        main_item = items_for_session[0]
        try:
            session_title = main_item.get('TITLE', '제목 없음')
            logger.info(f"Processing session ID {confer_num}: {session_title}")

            conf_date_val = None
            conf_date_str = main_item.get('CONF_DATE')
            if conf_date_str:
                try:
                    conf_date_val = datetime.strptime(conf_date_str,
                                                      '%Y년 %m월 %d일').date()
                except ValueError:
                    try:
                        conf_date_val = datetime.strptime(
                            conf_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(
                            f"Could not parse date: {conf_date_str}")

            era_co_val = f"제{main_item.get('DAE_NUM', 'N/A')}대"
            sess_val = ''
            dgr_val = ''
            title_parts = session_title.split(' ')
            if len(title_parts) > 1 and "회국회" in title_parts[1]:
                sess_val = title_parts[1].split('회국회')[0]
                if "(" in sess_val: sess_val = sess_val.split("(")[0]
            if len(title_parts) > 2 and "차" in title_parts[2]:
                dgr_val = title_parts[2].replace('차', '')

            session_defaults = {
                'era_co':
                era_co_val,
                'sess':
                sess_val,
                'dgr':
                dgr_val,
                'conf_dt':
                conf_date_val,
                'conf_knd':
                main_item.get('CLASS_NAME', '국회본회의'),
                'cmit_nm':
                main_item.get('CMIT_NAME',
                              main_item.get('CLASS_NAME', '국회본회의')),
                'down_url':
                main_item.get('PDF_LINK_URL', ''),
                'title':
                session_title,
                'bg_ptm':
                dt_time(9, 0)
            }

            if debug:
                logger.debug(
                    f"🐛 DEBUG PREVIEW: Would process session ID {confer_num}")
                continue

            session_obj, created = _process_session_item(
                session_defaults, confer_num)

            status_log = "✨ Created new session" if created else "🔄 Updated existing session" if force else "♻️ Session already exists"
            logger.info(f"{status_log}: {confer_num} - {session_title}")

            # --- DIRECTLY TRIGGER THE NEXT STEPS ---
            # This is the key fix. We no longer rely on fetch_session_details to do this.

            # 1. Fetch bills for this session.
            try:
                if is_celery_available():
                    fetch_session_bills.delay(session_id=confer_num,
                                              force=force,
                                              debug=debug)
                else:
                    # Call the wrapped function directly to avoid Celery registration issues
                    if hasattr(fetch_session_bills, '__wrapped__'):
                        fetch_session_bills.__wrapped__(self=None,
                                                        session_id=confer_num,
                                                        force=force,
                                                        debug=debug)
                    else:
                        fetch_session_bills(session_id=confer_num,
                                            force=force,
                                            debug=debug)
            except Exception as bills_error:
                logger.error(
                    f"Error fetching bills for session {confer_num}: {bills_error}"
                )

            # 2. Process the PDF if a URL exists.
            if session_obj.down_url:
                try:
                    if is_celery_available():
                        process_session_pdf.delay(session_id=confer_num,
                                                  force=force,
                                                  debug=debug)
                    else:
                        # Use the direct wrapper function to avoid Celery issues
                        process_session_pdf_direct(session_id=confer_num,
                                                   force=force,
                                                   debug=debug)
                except Exception as pdf_error:
                    logger.error(
                        f"Error processing PDF for session {confer_num}: {pdf_error}"
                    )
            else:
                logger.info(
                    f"No PDF URL for session {confer_num}, skipping PDF processing."
                )

        except Exception as e:
            logger.error(
                f"❌ Error processing session data for CONFER_NUM {confer_num}: {e}"
            )
            logger.exception("Full traceback for session processing error:")
            continue

    try:
        # Process each session item
        for confer_num, items_for_session in sessions_by_confer_num.items():
            connection.ensure_connection()
            main_item = items_for_session[0]
            try:
                # ... [existing session processing code] ...

                # 1. Fetch bills for this session.
                if is_celery_available():
                    fetch_session_bills.delay(session_id=confer_num,
                                              force=force,
                                              debug=debug)
                else:
                    fetch_session_bills(session_id=confer_num,
                                        force=force,
                                        debug=debug)

                # 2. Process the PDF if a URL exists.
                if session_obj.down_url:
                    if is_celery_available():
                        process_session_pdf.delay(session_id=confer_num,
                                                  force=force,
                                                  debug=debug)
                    else:
                        process_session_pdf(session_id=confer_num,
                                            force=force,
                                            debug=debug)
                else:
                    logger.info(
                        f"No PDF URL for session {confer_num}, skipping PDF processing."
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error processing session data for CONFER_NUM {confer_num}: {e}"
                )
                logger.exception(
                    "Full traceback for session processing error:")
                continue

        logger.info(
            f"🎉 Sessions processing complete: {created_count} created, {updated_count} updated."
        )

    except RequestException as re_exc:
        error_msg = f"API request failed while processing sessions: {str(re_exc)}"
        logger.error(error_msg)
        try:
            self.retry(exc=RequestException(error_msg))
        except MaxRetriesExceededError:
            logger.error(
                "❌ Max retries (3) reached for session details API request")
            raise

    except json.JSONDecodeError as json_e:
        error_msg = f"Failed to parse API response as JSON: {str(json_e)}"
        logger.error(error_msg)
        # Don't retry JSON decode errors as they indicate malformed response
        raise ValueError(error_msg)

    except Exception as e:
        error_msg = f"Unexpected error in process_sessions_data: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.exception("Stack trace for debugging:")
        try:
            self.retry(exc=Exception(error_msg))
        except MaxRetriesExceededError:
            logger.error("❌ Max retries (3) reached after unexpected error")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self,
                        session_id=None,
                        force=False,
                        debug=False):  # Celery provides 'self'
    """Fetch bills for a specific session using VCONFBILLLIST API."""
    if not session_id:
        logger.error("session_id is required for fetch_session_bills.")
        return

    logger.info(
        f"🔍 Fetching bills for session: {session_id} (force={force}, debug={debug})"
    )
    if debug:
        logger.debug(
            f"🐛 DEBUG: Fetching bills for session {session_id} in debug mode")

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("ASSEMBLY_API_KEY not configured.")
            return

        formatted_conf_id = format_conf_id(session_id)
        url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": formatted_conf_id,
            "pSize": 500
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if debug:
            logger.debug(
                f"🐛 DEBUG: Full VCONFBILLLIST response for {session_id}: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        bills_data_list = []
        api_key_name = 'VCONFBILLLIST'
        if data and api_key_name in data and isinstance(
                data[api_key_name], list):
            if len(data[api_key_name]) > 1 and isinstance(
                    data[api_key_name][1], dict):
                bills_data_list = data[api_key_name][1].get('row', [])
            elif len(data[api_key_name]) > 0 and isinstance(
                    data[api_key_name][0], dict):
                head_info = data[api_key_name][0].get('head')
                if head_info and head_info[0].get('RESULT', {}).get(
                        'CODE', '').startswith("INFO-200"):
                    logger.info(
                        f"API result for VCONFBILLLIST ({session_id}) indicates no bill data (INFO-200)."
                    )
                elif 'row' in data[api_key_name][
                        0]:  # Fallback for inconsistent structure
                    bills_data_list = data[api_key_name][0].get('row', [])

        if not bills_data_list:
            logger.info(
                f"ℹ️ No bills found from VCONFBILLLIST API for session {session_id}."
            )
            return

        if debug:
            logger.debug(
                f"🐛 DEBUG: Found {len(bills_data_list)} bills for session {session_id} from API."
            )
        else:
            try:
                session_obj = Session.objects.get(conf_id=session_id)
            except Session.DoesNotExist:
                logger.error(
                    f"❌ Session {session_id} not found in database when fetching bills. Cannot associate bills."
                )
                return

            created_count = 0
            updated_count = 0
            bill_id_api_list = []
            for bill_item in bills_data_list:
                bill_id_api = bill_item.get('BILL_ID')
                if not bill_id_api:
                    logger.warning(
                        f"Skipping bill item due to missing BILL_ID in session {session_id}: {bill_item.get('BILL_NM', 'N/A')}"
                    )
                    continue

                # Extract proposer information from multiple sources
                proposer_info = "국회"  # Default fallback

                # First try PROPOSER field from VCONFBILLLIST
                bill_proposer = bill_item.get('PROPOSER', '').strip()

                # If no PROPOSER, try to get from session's CMIT_NM (from VCONFDETAIL)
                if not bill_proposer and hasattr(
                        session_obj, 'cmit_nm') and session_obj.cmit_nm:
                    bill_proposer = session_obj.cmit_nm.strip()

                # Define institutional/non-individual proposers that should not be looked up
                institutional_proposers = [
                    '국회본회의', '국회', '본회의', '정부', '대통령', '국무총리', '행정부', '정부제출',
                    '의장', '부의장', '국회의장', '국회부의장'
                ]

                # Always use generic proposer initially, then fetch detailed info from BILLINFODETAIL
                proposer_info = bill_proposer if bill_proposer else "국회본회의"
                logger.info(
                    f"📝 Bill {bill_id_api} initial proposer: {proposer_info} - will fetch detailed info from BILLINFODETAIL"
                )

                bill_defaults = {
                    'session': session_obj,
                    'bill_nm': bill_item.get('BILL_NM', ''),
                }
                if bill_item.get('BILL_NO'):
                    bill_defaults['bill_no'] = bill_item.get('BILL_NO')
                if bill_item.get('PROPOSE_DT'):
                    bill_defaults['propose_dt'] = bill_item.get('PROPOSE_DT')

                bill_obj, created = Bill.objects.update_or_create(
                    bill_id=
                    bill_id_api,  # BILL_ID from API is the primary key for bills
                    defaults=bill_defaults)

                if created:
                    created_count += 1
                    logger.info(
                        f"✨ Created new bill: {bill_id_api} ({bill_obj.bill_nm[:30]}...) initial proposer: {proposer_info} for session {session_id}"
                    )
                else:  # Bill already existed, update_or_create updated it
                    updated_count += 1
                    logger.info(
                        f"🔄 Updated existing bill: {bill_id_api} ({bill_obj.bill_nm[:30]}...) initial proposer: {proposer_info} for session {session_id}"
                    )

                # ALWAYS fetch detailed information from BILLINFODETAIL to get real proposer data
                if not debug:
                    logger.info(
                        f"🔍 Fetching detailed proposer info from BILLINFODETAIL for bill {bill_id_api}"
                    )
                    if is_celery_available():
                        fetch_bill_detail_info.delay(bill_id_api,
                                                     force=True,
                                                     debug=debug)
                    else:
                        fetch_bill_detail_info(bill_id_api,
                                               force=True,
                                               debug=debug)
            logger.info(
                f"🎉 Bills processed for session {session_id}: {created_count} created, {updated_count} updated."
            )

    except RequestException as re_exc:
        logger.error(
            f"Request error fetching bills for session {session_id}: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for session bills {session_id}.")
    except json.JSONDecodeError as json_e:
        logger.error(
            f"JSON decode error for session {session_id} bills: {json_e}")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching bills for session {session_id}: {e}")
        logger.exception(
            f"Full traceback for session {session_id} bill fetch:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected error for bills of {session_id}."
            )
        # raise # Optionally


def get_session_bills_list(session_id):
    """
    Get list of BILL_NM (bill names) for a specific session_id using nwvrqwxyaytdsfvhu API.
    Note: This API provides BILL_NM but VCONFBILLLIST is usually preferred for bills related to a *specific meeting instance (CONF_ID)*.
    This function seems to be for general bill listing by CONF_NUM (which might be session number rather than meeting ID).
    Clarify if CONF_NUM here is the same as Session.conf_id.
    """
    try:
        # Check API key: Assuming 'ASSEMBLY_API_KEY' for consistency,
        # or if 'OPEN_ASSEMBLY_API_KEY' is a separate, valid key.
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            # if not hasattr(settings, 'OPEN_ASSEMBLY_API_KEY') or not settings.OPEN_ASSEMBLY_API_KEY: # If it's a different key
            logger.error("API Key not configured for get_session_bills_list.")
            return []

        api_url = "https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu"
        params = {
            'KEY':
            settings.ASSEMBLY_API_KEY,  # Or settings.OPEN_ASSEMBLY_API_KEY
            'Type': 'json',
            'pIndex': 1,
            'pSize': 1000,  # Max allowed, or paginate if more
            'CONF_NUM': str(
                session_id
            )  # API expects string, ensure session_id is appropriate for CONF_NUM
        }

        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        bill_names = []
        api_key_name_bills = 'nwvrqwxyaytdsfvhu'
        if data and api_key_name_bills in data and isinstance(
                data[api_key_name_bills], list):
            if len(data[api_key_name_bills]) > 1 and isinstance(
                    data[api_key_name_bills][1], dict):
                rows = data[api_key_name_bills][1].get('row', [])
                for bill_data_item in rows:
                    if bill_data_item.get('BILL_NM'):
                        bill_names.append(bill_data_item['BILL_NM'])
            # Add handling for other structures or head info codes if necessary

        logger.info(
            f"Found {len(bill_names)} bill names for CONF_NUM {session_id} via nwvrqwxyaytdsfvhu."
        )
        return bill_names

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Network error getting bills for session/conf_num {session_id} (nwvrqwxyaytdsfvhu): {e}"
        )
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON parsing error for bills of session/conf_num {session_id} (nwvrqwxyaytdsfvhu): {e}"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error getting bill names for session/conf_num {session_id} (nwvrqwxyaytdsfvhu): {e}"
        )
    return []


@with_db_retry
def get_session_bill_names(session_id):
    """Get list of bill names for a specific session (CONF_ID) from already stored Bills."""
    try:
        session = Session.objects.get(conf_id=session_id)
        bills = Bill.objects.filter(session=session).values_list('bill_nm',
                                                                 flat=True)
        return list(bill for bill in bills
                    if bill)  # Filter out empty/None names
    except Session.DoesNotExist:
        logger.error(
            f"Session {session_id} not found when trying to get its bill names from DB."
        )
    except Exception as e:
        logger.error(
            f"❌ Error fetching stored bill names for session {session_id}: {e}"
        )
    return []


def extract_text_segment(text, start_marker, end_marker=None):
    """
    Extract text segment. If start_marker is empty, starts from beginning.
    If end_marker is empty or not found, goes to end of text.
    Start_pos is *after* the start_marker.
    """
    try:
        if not text: return ""

        start_pos = 0
        if start_marker:
            found_pos = text.find(start_marker)
            if found_pos == -1:
                return ""  # Start marker not found
            start_pos = found_pos + len(
                start_marker)  # Segment starts AFTER the marker

        end_pos = len(text)  # Default to end of text
        if end_marker:
            found_end_pos = text.find(end_marker, start_pos)
            if found_end_pos != -1:
                end_pos = found_end_pos  # Segment ends BEFORE the end_marker

        segment = text[start_pos:end_pos].strip()
        return segment

    except Exception as e:
        logger.error(
            f"❌ Error extracting text segment ('{start_marker}' to '{end_marker}'): {e}"
        )
        return ""


def extract_bill_specific_content(full_text, bill_name):
    """Extract content specific to a bill from the full text using keyword matching."""
    try:
        if not full_text or not bill_name:
            return ""

        # Clean bill name for better matching
        clean_bill_name = bill_name.strip()

        # Create variations of the bill name for searching
        search_terms = [clean_bill_name]

        # Add variations without common suffixes
        if "법률안" in clean_bill_name:
            search_terms.append(clean_bill_name.replace("법률안", ""))
        if "일부개정" in clean_bill_name:
            search_terms.append(clean_bill_name.replace("일부개정", ""))

        # Extract core bill name (before parentheses if any)
        if "(" in clean_bill_name:
            core_name = clean_bill_name.split("(")[0].strip()
            search_terms.append(core_name)

        # Find all mentions of the bill in the text
        bill_positions = []
        for term in search_terms:
            if len(term.strip()) > 3:  # Only search for meaningful terms
                pos = 0
                while True:
                    found_pos = full_text.find(term, pos)
                    if found_pos == -1:
                        break
                    bill_positions.append(found_pos)
                    pos = found_pos + 1

        if not bill_positions:
            logger.info(f"No mentions found for bill: {bill_name}")
            return ""

        # Find the earliest mention
        earliest_pos = min(bill_positions)

        # Extract content from the earliest mention to a reasonable endpoint
        # Look for next bill mention or use chunk size
        start_pos = max(0, earliest_pos - 500)  # Include some context before

        # Find a good end point (next bill, end of section, or max length)
        max_segment_length = 15000  # 15k chars max per bill segment
        end_pos = min(len(full_text), start_pos + max_segment_length)

        # Try to find a natural break point (like next bill discussion)
        remaining_text = full_text[earliest_pos + len(clean_bill_name):end_pos]

        # Look for patterns that might indicate next bill discussion
        next_bill_patterns = ["○", "의안", "법률안", "건의"]
        for pattern in next_bill_patterns:
            pattern_pos = remaining_text.find(pattern)
            if pattern_pos != -1 and pattern_pos > 1000:  # At least 1k chars into the segment
                end_pos = earliest_pos + len(clean_bill_name) + pattern_pos
                break

        extracted_content = full_text[start_pos:end_pos].strip()

        logger.info(
            f"Extracted {len(extracted_content)} chars for bill: {bill_name[:50]}..."
        )
        return extracted_content

    except Exception as e:
        logger.error(
            f"❌ Error extracting bill-specific content for '{bill_name}': {e}")
        return ""


@with_db_retry
def get_all_assembly_members():
    """Get all assembly member names from local Speaker database."""
    try:
        # Ensure fresh database connection
        from django.db import connection
        from .models import Speaker
        connection.ensure_connection()

        # Get all speaker names from our local database
        speaker_names = set(Speaker.objects.values_list('naas_nm', flat=True))
        logger.info(
            f"✅ Using {len(speaker_names)} assembly member names from local database"
        )
        return speaker_names
    except Exception as e:
        logger.error(f"❌ Error fetching assembly members from database: {e}")
        return set()


# Filter to ignore non-의원 speakers - only 의원 can vote legally
IGNORED_SPEAKERS = [
    '우원식',  # Current 국회의장
    '이학영',  # 부의장
    '정우택',  # 부의장  
    '의장',
    '부의장',
    '위원장',
    '국무총리',
    '장관',
    '차관',
    '실장',
    '청장',
    '원장',
    '대변인',
    '비서관',
    '수석',
    '정무위원',
    '간사'
]


def extract_statements_for_bill_segment(bill_text_segment,
                                        session_id,
                                        bill_name,
                                        debug=False):
    """Extract statements using LLM for index-based segmentation, then batch process."""
    if not bill_text_segment:
        return []

    logger.info(
        f"🔍 Processing bill segment: '{bill_name}' (session: {session_id}) - {len(bill_text_segment)} chars"
    )

    # Step 1: Get speech segment indices from LLM
    speech_indices = get_speech_segment_indices_from_llm(
        bill_text_segment, bill_name, debug)

    if not speech_indices:
        logger.info(
            f"No speech segments found for bill '{bill_name}', trying ◯ fallback"
        )
        return process_single_segment_for_statements_with_splitting(
            bill_text_segment, session_id, bill_name, debug)

    # Step 2: Extract speech segments using indices
    speech_segments = []
    for idx_pair in speech_indices:
        start_idx = idx_pair.get('start', 0)
        end_idx = idx_pair.get('end', len(bill_text_segment))

        # Validate indices
        start_idx = max(0, min(start_idx, len(bill_text_segment)))
        end_idx = max(start_idx, min(end_idx, len(bill_text_segment)))

        if end_idx > start_idx:
            segment_text = bill_text_segment[start_idx:end_idx].strip()
            if segment_text and len(
                    segment_text) > 50:  # Minimum meaningful content
                speech_segments.append(segment_text)

    logger.info(
        f"Extracted {len(speech_segments)} speech segments using LLM indices")

    # Step 3: Batch process the extracted segments
    if speech_segments:
        return process_speech_segments_multithreaded(speech_segments,
                                                     session_id, bill_name,
                                                     debug)
    else:
        logger.info(f"No valid speech segments extracted, using fallback")
        return process_single_segment_for_statements_with_splitting(
            bill_text_segment, session_id, bill_name, debug)


def process_single_segment_for_statements_with_splitting(
        bill_text_segment, session_id, bill_name, debug=False):
    """Process a single text segment by splitting at ◯ markers and analyzing each speech individually with multithreading."""
    if not bill_text_segment:
        return []

    logger.info(
        f"🔍 Stage 2 (◯ Splitting): For bill '{bill_name}' (session: {session_id}) - {len(bill_text_segment)} chars"
    )

    # Find all ◯ markers to determine individual speeches
    speaker_markers = []
    for i, char in enumerate(bill_text_segment):
        if char == '◯':
            speaker_markers.append(i)

    if len(speaker_markers) < 1:
        logger.info(f"No ◯ markers found, skipping segment")
        return []

    # Split at each ◯ marker to create individual speech segments
    speech_segments = []

    # Create segments between each ◯ marker
    for i in range(len(speaker_markers)):
        start_pos = speaker_markers[i]
        if i + 1 < len(speaker_markers):
            end_pos = speaker_markers[i + 1]
        else:
            end_pos = len(bill_text_segment)

        segment = bill_text_segment[start_pos:end_pos].strip()
        if segment and len(
                segment) > 50:  # Only process segments with meaningful content
            speech_segments.append(segment)

    logger.info(
        f"Split text into {len(speech_segments)} individual speech segments based on ◯ markers. "
        f"Segment sizes: {[len(seg) for seg in speech_segments]} chars")

    # Process segments with multithreading for LLM calls
    all_statements = process_speech_segments_multithreaded(
        speech_segments, session_id, bill_name, debug)

    logger.info(
        f"✅ ◯-based processing for '{bill_name}' resulted in {len(all_statements)} statements "
        f"from {len(speech_segments)} speech segments")

    return all_statements


def process_speech_segments_multithreaded(speech_segments,
                                          session_id,
                                          bill_name,
                                          debug=False):
    """Process multiple speech segments with true parallel processing using batch analysis."""
    if not speech_segments:
        return []

    if debug:
        logger.debug(
            f"🐛 DEBUG: Would process {len(speech_segments)} segments in parallel batch"
        )
        return []

    logger.info(
        f"🚀 Processing {len(speech_segments)} speech segments in parallel batch for bill '{bill_name}'"
    )

    # Use the new batch processing function
    all_statements = analyze_speech_segment_with_llm_batch(
        speech_segments, session_id, bill_name, debug)

    logger.info(
        f"🎉 Parallel batch processing completed for '{bill_name}': {len(all_statements)} valid statements from {len(speech_segments)} segments"
    )
    return all_statements


def process_single_segment_for_statements(bill_text_segment,
                                          session_id,
                                          bill_name,
                                          debug=False):
    """Fallback: Use splitting approach for single segments."""
    return process_single_segment_for_statements_with_splitting(
        bill_text_segment, session_id, bill_name, debug)


def get_speech_segment_indices_from_llm(text_segment, bill_name, debug=False):
    """Use LLM to identify speech segment boundaries and return start/end indices with batch processing."""
    if not genai or debug:
        return []

    logger.info(
        f"🎯 Getting speech segment indices for bill '{bill_name[:50]}...' ({len(text_segment)} chars)"
    )

    # Batch processing configuration
    MAX_SEGMENTATION_LENGTH = 50000  # 50k chars per batch
    BATCH_OVERLAP = 5000  # 5k character overlap between batches

    if len(text_segment) <= MAX_SEGMENTATION_LENGTH:
        # Single batch processing
        return _process_single_segmentation_batch(text_segment, bill_name, 0)

    # Multi-batch processing for large texts
    logger.info(
        f"🔄 Processing large text in batches (max {MAX_SEGMENTATION_LENGTH} chars per batch)"
    )

    all_indices = []
    batch_start = 0
    batch_count = 0

    while batch_start < len(text_segment):
        batch_end = min(batch_start + MAX_SEGMENTATION_LENGTH,
                        len(text_segment))
        batch_text = text_segment[batch_start:batch_end]
        batch_count += 1

        logger.info(
            f"📦 Processing batch {batch_count}: chars {batch_start}-{batch_end}"
        )

        # Process this batch
        batch_indices = _process_single_segmentation_batch(
            batch_text, bill_name, batch_start)

        if batch_indices:
            # Adjust indices to be relative to the full document
            adjusted_indices = []
            for idx_pair in batch_indices:
                adjusted_start = idx_pair['start'] + batch_start
                adjusted_end = idx_pair['end'] + batch_start

                # Ensure indices don't exceed the full document length
                if adjusted_start < len(text_segment) and adjusted_end <= len(
                        text_segment):
                    adjusted_indices.append({
                        'start': adjusted_start,
                        'end': adjusted_end
                    })

            all_indices.extend(adjusted_indices)
            logger.info(
                f"✅ Batch {batch_count}: Found {len(adjusted_indices)} speech segments"
            )
        else:
            logger.info(f"⚠️ Batch {batch_count}: No speech segments found")

        # Move to next batch with overlap
        if batch_end >= len(text_segment):
            break

        batch_start = batch_end - BATCH_OVERLAP

        # Rate limiting between batches
        if batch_start < len(text_segment):
            logger.info("⏳ Resting 3s before next batch...")
            time.sleep(3)

    # Remove overlapping segments and sort by start position
    deduplicated_indices = _deduplicate_speech_segments(all_indices)

    logger.info(
        f"🎉 Batch processing complete: {len(deduplicated_indices)} total speech segments from {batch_count} batches"
    )
    return deduplicated_indices


def _process_single_segmentation_batch(text_segment, bill_name, offset):
    """Process a single text segment for speech segmentation indices."""
    try:
        # Create basic indices by splitting at ◯ markers as fallback
        speech_indices = []
        current_pos = 0

        while True:
            marker_pos = text_segment.find('◯', current_pos)
            if marker_pos == -1:
                break

            # Look for next marker to determine end
            next_marker_pos = text_segment.find('◯', marker_pos + 1)
            end_pos = next_marker_pos if next_marker_pos != -1 else len(
                text_segment)

            # Only include segments with meaningful content
            segment_length = end_pos - marker_pos
            if segment_length > 100:  # Minimum segment size
                speech_indices.append({
                    'start': marker_pos + offset,
                    'end': end_pos + offset
                })

            current_pos = marker_pos + 1

        logger.info(
            f"Found {len(speech_indices)} speech segments using ◯ marker fallback"
        )
        return speech_indices

    except Exception as e:
        logger.error(f"Error in single segmentation batch: {e}")
        return []


def fetch_continuous_sessions_direct(force=False,
                                     debug=False,
                                     start_date=None):
    """
    Direct (non-Celery) version of fetch_continuous_sessions for management commands.
    """
    logger.info(
        f"🔍 Starting continuous session fetch (direct) (force={force}, debug={debug}, start_date={start_date})"
    )

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("❌ ASSEMBLY_API_KEY not configured")
            raise ValueError("ASSEMBLY_API_KEY not configured")

        url = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
            except ValueError:
                logger.error(
                    f"Invalid start_date format: {start_date}. Expected ISO format (YYYY-MM-DD)."
                )
                return
            logger.info(
                f"📅 Continuing from date: {start_datetime.strftime('%Y-%m')}")
        else:
            start_datetime = datetime.now()
            logger.info(
                f"📅 Starting from current date: {start_datetime.strftime('%Y-%m')}"
            )

        current_date = start_datetime
        sessions_found_in_period = False
        DAE_NUM_TARGET = "22"

        # Go back up to 36 months
        for months_back in range(0, 36):
            target_date = current_date - timedelta(days=months_back * 30.44)
            conf_date_str = target_date.strftime('%Y-%m')

            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "DAE_NUM": DAE_NUM_TARGET,
                "CONF_DATE": conf_date_str,
                "pSize": 500
            }

            logger.info(f"📅 Fetching sessions for: {conf_date_str}")
            if debug:
                logger.debug(f"🐛 DEBUG: API URL: {url}, Params: {params}")

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if debug:
                    logger.debug(
                        f"🐛 DEBUG: API Response status for {conf_date_str}: {response.status_code}"
                    )

                sessions_data = extract_sessions_from_response(data,
                                                               debug=debug)

                if sessions_data:
                    sessions_found_in_period = True
                    logger.info(
                        f"✅ Found {len(sessions_data)} session items for {conf_date_str}"
                    )
                    process_sessions_data(sessions_data,
                                          force=force,
                                          debug=debug)
                    if not debug: time.sleep(1)
                else:
                    logger.info(f"❌ No sessions found for {conf_date_str}")
                    if months_back > 6 and not sessions_found_in_period:
                        logger.info(
                            "🛑 No sessions found in recent ~6 months of search, stopping."
                        )
                        break
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"⚠️ Request error fetching {conf_date_str}: {e}")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ JSON parsing error for {conf_date_str}: {e}")
            except Exception as e:
                logger.warning(
                    f"⚠️ Unexpected error fetching/processing {conf_date_str}: {e}"
                )
                if debug:
                    logger.exception("Full traceback for error during loop:")
            continue

        if not debug and sessions_found_in_period:
            logger.info("🔄 Triggering additional data collection...")
            fetch_additional_data_nepjpxkkabqiqpbvk(force=force, debug=debug)

        if sessions_found_in_period:
            logger.info("🎉 Continuous session fetch attempt completed.")
        else:
            logger.info(
                "ℹ️ No new sessions found during this continuous fetch period."
            )

    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
    except Exception as e:
        logger.error(
            f"❌ Critical error in fetch_continuous_sessions_direct: {e}")
        logger.exception("Full traceback for critical error:")


def process_session_pdf_direct(session_id=None, force=False, debug=False):
    """
    Direct wrapper for process_session_pdf that can be called without Celery.
    This is useful for management commands and testing.
    """
    # Call the underlying function directly without the Celery task wrapper
    if not session_id:
        logger.error("session_id is required for process_session_pdf.")
        return

    logger.info(
        f"📄 Processing PDF for session: {session_id} (force={force}, debug={debug}) [DIRECT CALL]"
    )

    try:
        session = Session.objects.get(conf_id=session_id)
    except Session.DoesNotExist:
        logger.error(
            f"❌ Session {session_id} not found in DB. Cannot process PDF.")
        return

    if not session.down_url:
        logger.info(
            f"ℹ️ No PDF URL for session {session_id}. Skipping PDF processing."
        )
        return

    if Statement.objects.filter(
            session=session).exists() and not force and not debug:
        logger.info(
            f"Statements already exist for session {session_id} and not in force/debug mode. Skipping."
        )
        return

    if debug:
        logger.debug(f"🐛 DEBUG: Simulating PDF processing for {session_id}.")
        return

    temp_pdf_path = None
    try:
        logger.info(f"📥 Downloading PDF from: {session.down_url}")
        response = requests.get(session.down_url, timeout=120, stream=True)
        response.raise_for_status()

        temp_dir = Path(getattr(settings, "TEMP_FILE_DIR", "temp_files"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_pdf_path = temp_dir / f"session_{session_id}_{int(time.time())}.pdf"

        with open(temp_pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(
            f"📥 PDF for session {session_id} downloaded to {temp_pdf_path}")

        full_text = ""
        with pdfplumber.open(temp_pdf_path) as pdf:
            pages = pdf.pages
            logger.info(f"Extracting text from {len(pages)} pages...")
            for i, page in enumerate(pages):
                page_text = page.extract_text(x_tolerance=1, y_tolerance=3)
                if page_text:
                    full_text += page_text + "\n"
                if (i + 1) % 20 == 0:
                    logger.info(f"Processed {i+1}/{len(pages)} pages...")
        logger.info(f"📄 Extracted ~{len(full_text)} chars from PDF.")

        if not full_text.strip():
            logger.warning(
                f"Extracted text is empty for session {session_id}.")
            return

        # Fetch the list of bills from the database
        bills_for_session = get_session_bill_names(session_id)

        # Process the PDF text for statements
        process_session_pdf_text(
            full_text,
            session_id,
            session,
            None,  # bills_context_str is no longer needed
            bills_for_session,  # Pass the list of bills from the DB
            debug)

    except RequestException as re_exc:
        logger.error(
            f"Request error downloading PDF for session {session_id}: {re_exc}"
        )
        # Don't retry in direct calls
    except Exception as e:
        logger.error(
            f"❌ Unexpected error processing PDF for session {session_id}: {e}")
        logger.exception(f"Full traceback for PDF processing {session_id}:")
    finally:
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.info(f"🗑️ Deleted temporary PDF: {temp_pdf_path}")
            except OSError as e_del:
                logger.error(
                    f"Error deleting temporary PDF {temp_pdf_path}: {e_del}")


def _deduplicate_speech_segments(all_indices):
    """Remove overlapping speech segments and return sorted unique segments."""
    if not all_indices:
        return []

    # Sort by start position
    sorted_indices = sorted(all_indices, key=lambda x: x['start'])

    deduplicated = []
    last_end = -1

    for segment in sorted_indices:
        start = segment['start']
        end = segment['end']

        # Skip if this segment overlaps significantly with the previous one
        if start < last_end - 1000:  # Allow small overlap of 1000 chars
            continue

        # Adjust start if there's minor overlap
        if start < last_end:
            start = last_end

        # Only add if the segment is still meaningful
        if end - start > 50:  # Minimum 50 chars
            deduplicated.append({'start': start, 'end': end})
            last_end = end

    logger.info(
        f"🔧 Deduplicated {len(all_indices)} segments to {len(deduplicated)} unique segments"
    )
    return deduplicated


def analyze_speech_segment_with_llm_batch(speech_segments,
                                          session_id,
                                          bill_name,
                                          debug=False):
    """Batch analyze multiple speech segments with LLM - 20 statements per request using new google.genai structure."""
    global client

    if not client:
        logger.warning(
            "❌ Gemini not available. Cannot analyze speech segments.")
        return []

    if not speech_segments:
        return []

    logger.info(
        f"🚀 Batch analyzing {len(speech_segments)} speech segments for bill '{bill_name[:50]}...' using gemini-2.0-flash"
    )

    # Get assembly members once for the entire batch
    assembly_members = get_all_assembly_members()

    results = []
    batch_size = 20  # Process 20 statements per request

    # Split into batches of 20
    for batch_start in range(0, len(speech_segments), batch_size):
        batch_end = min(batch_start + batch_size, len(speech_segments))
        batch_segments = speech_segments[batch_start:batch_end]

        logger.info(
            f"Processing batch {batch_start//batch_size + 1}/{(len(speech_segments)-1)//batch_size + 1}: segments {batch_start}-{batch_end-1}"
        )

        # Estimate total tokens for the batch
        total_chars = sum(len(segment) for segment in batch_segments)
        estimated_tokens = total_chars // 4 + 1000  # Rough estimate with overhead

        # Wait if needed before submitting
        if not gemini_rate_limiter.wait_if_needed(estimated_tokens):
            logger.warning(
                f"Skipping batch {batch_start//batch_size + 1} due to rate limiting timeout"
            )
            continue

        # Create batch prompt for 20 statements
        try:
            batch_results = analyze_batch_statements_single_request(
                batch_segments, bill_name, assembly_members, estimated_tokens,
                batch_start)
            results.extend(batch_results)

            # Record successful API usage
            gemini_rate_limiter.record_request(estimated_tokens, success=True)

        except Exception as e:
            # Record failed API usage
            error_type = "timeout" if "timeout" in str(
                e).lower() else "api_error"
            gemini_rate_limiter.record_error(error_type)
            logger.error(f"Batch analysis failed: {e}")
            continue

        # Brief pause between batches
        if batch_end < len(speech_segments):
            logger.info(f"Resting 3s before next batch...")
            time.sleep(3)

    logger.info(
        f"✅ Batch analysis completed: {len(results)} valid statements from {len(speech_segments)} segments"
    )
    return sorted(results, key=lambda x: x.get('segment_index', 0))


def analyze_batch_statements_single_request(batch_segments, bill_name,
                                            assembly_members, estimated_tokens,
                                            batch_start_index):
    """Analyze up to 20 statements in a single API request with improved batching using new google.genai structure."""
    if not batch_segments:
        return []

    # Process large segments by chunking them
    processed_segments = []
    for segment in batch_segments:
        if len(segment) > 2000:  # If segment is too large, split it
            # Split at ◯ markers to preserve speech boundaries
            sub_segments = segment.split('◯')
            for i, sub_seg in enumerate(sub_segments):
                if sub_seg.strip() and len(sub_seg.strip()) > 50:
                    # Add back the ◯ marker except for first segment
                    final_seg = ('◯' + sub_seg) if i > 0 else sub_seg
                    processed_segments.append(final_seg.strip())
        else:
            processed_segments.append(segment)

    # Limit to manageable batch size
    max_segments_per_batch = 15  # Reduced for better reliability
    if len(processed_segments) > max_segments_per_batch:
        processed_segments = processed_segments[:max_segments_per_batch]

    # Clean and prepare segments
    cleaned_segments = []
    for segment in processed_segments:
        # Remove newlines and clean text
        cleaned_segment = segment.replace('\n', ' ').replace('\r', '').strip()

        # Stop at reporting end marker
        report_end_marker = "(보고사항은 끝에 실음)"
        if report_end_marker in cleaned_segment:
            cleaned_segment = cleaned_segment.split(
                report_end_marker)[0].strip()

        # Limit segment length but be more generous
        if len(cleaned_segment) > 1000:
            cleaned_segment = cleaned_segment[:1000] + "..."

        if cleaned_segment and len(cleaned_segment.strip()) > 20:
            cleaned_segments.append(cleaned_segment)

    if not cleaned_segments:
        logger.warning("No valid segments after cleaning and processing")
        return []

    # Create safe bill name
    safe_bill_name = str(bill_name)[:100] if bill_name else "알 수 없는 의안"

    # Create batch prompt for multiple segments
    segments_text = ""
    for i, segment in enumerate(cleaned_segments):
        segments_text += f"\n--- 구간 {i+1} ---\n{segment}\n"

    # Split prompt if too large
    max_prompt_length = 15000  # Conservative limit
    if len(segments_text) > max_prompt_length:
        # Process in smaller sub-batches
        return _process_large_batch_in_chunks(cleaned_segments, bill_name,
                                              assembly_members,
                                              estimated_tokens,
                                              batch_start_index)

    prompt = f"""
당신은 역사에 길이 남을 기록가입니다. 당신의 기록과 분류, 그리고 정확도는 미래에 사람들을 살릴 것입니다. 당신이 정확하게 기록을 해야만 사람들은 그 정확한 기록에 의존하여 살아갈 수 있을 것입니다. 따라서, 다음 명령을 아주 자세히, 엄밀히, 수행해 주십시오.
국회 발언 분석 요청:

의안: {safe_bill_name}

발언 구간들:
{segments_text}

다음 JSON 배열로 응답하세요:
[
  {{
    "segment_index": 1,
    "speaker_name": "발언자명",
    "start_idx": 0,
    "end_idx": 100,
    "is_valid_member": true,
    "is_substantial": true,
    "sentiment_score": 0.0,
    "bill_relevance_score": 0.5
  }}
]

규칙:
- ◯로 시작하는 실제 의원 발언만 포함
- 의사진행 발언자 제외
- 발언자명에서 직책 제거
- JSON 배열만 응답"""

    return _execute_batch_analysis(prompt, cleaned_segments,
                                   processed_segments, assembly_members,
                                   batch_start_index, bill_name)


def _process_large_batch_in_chunks(batch_model, segments, bill_name,
                                   assembly_members, estimated_tokens,
                                   batch_start_index):
    """Process large batches by splitting into smaller chunks."""
    chunk_size = 8  # Process 8 segments at a time
    all_results = []

    for chunk_start in range(0, len(segments), chunk_size):
        chunk_end = min(chunk_start + chunk_size, len(segments))
        chunk_segments = segments[chunk_start:chunk_end]

        chunk_results = analyze_batch_statements_single_request(
            batch_model, chunk_segments, bill_name, assembly_members,
            estimated_tokens // (len(segments) // chunk_size + 1),
            batch_start_index + chunk_start)

        all_results.extend(chunk_results)

        # Brief pause between chunks
        if chunk_end < len(segments):
            time.sleep(1)

    return all_results


def _execute_batch_analysis(prompt,
                            cleaned_segments,
                            original_segments,
                            assembly_members,
                            batch_start_index,
                            bill_name,
                            max_retries=3):
    """Execute the actual batch analysis request with retry logic for API errors using new google.genai structure."""
    global client

    if not client:
        logger.error("Gemini client not initialized for batch analysis.")
        return []

    for attempt in range(max_retries + 1):
        start_time = time.time()
        try:
            if GENAI_AVAILABLE and hasattr(client, 'models'):
                # Use new google.genai structure
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="text/plain"))
                response_text_raw = response.text
            elif GENAI_LEGACY_AVAILABLE:
                # Use legacy google.generativeai
                model = client.GenerativeModel("gemini-2.0-flash")
                response = model.generate_content(prompt)
                response_text_raw = response.text
            else:
                logger.error("No available Gemini API client for batch analysis")
                return []

            processing_time = time.time() - start_time
            logger.info(
                f"Batch processing took {processing_time:.1f}s for {len(cleaned_segments)} segments"
            )

            if not response_text_raw:
                logger.warning(
                    f"Empty batch response from LLM after {processing_time:.1f}s"
                )
                return []

            response_text_cleaned = response_text_raw.strip().replace(
                "```json", "").replace("```", "").strip()

            try:
                analysis_array = json.loads(response_text_cleaned)
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in batch response: {e}")
                logger.debug(f"Raw response: {response_text_cleaned[:500]}...")
                return []

            if not isinstance(analysis_array, list):
                logger.warning(f"Expected list but got {type(analysis_array)}")
                return []

            results = []
            # --- BEGIN: DB Policy Category Attachment ---
            # Try to fetch the Bill object for bill_name (if available)
            bill_obj = None
            main_policy_category = None
            policy_subcategories = []
            if bill_name:
                try:
                    from .models import Bill
                    bill_obj = Bill.objects.filter(
                        bill_nm__icontains=bill_name).order_by(
                            '-created_at').first()
                    if bill_obj:
                        # Main policy category (list of names, highest confidence first)
                        main_policy_category = list(
                            bill_obj.category_mappings.filter(is_primary=True).
                            order_by('-confidence_score').values_list(
                                'category__name', flat=True))
                        # Policy subcategories (list of names, highest relevance first)
                        policy_subcategories = list(
                            bill_obj.subcategory_mappings.order_by(
                                '-relevance_score').values_list(
                                    'subcategory__name', flat=True))
                except Exception as cat_exc:
                    logger.warning(
                        f"Could not fetch policy categories for bill '{bill_name}': {cat_exc}"
                    )
            # --- END: DB Policy Category Attachment ---
            for i, analysis_json in enumerate(analysis_array):
                if not isinstance(analysis_json, dict):
                    continue

                speaker_name = analysis_json.get('speaker_name', '').strip()
                start_idx = analysis_json.get('start_idx', 0)
                end_idx = analysis_json.get('end_idx', 0)
                is_valid_member = analysis_json.get('is_valid_member', False)
                is_substantial = analysis_json.get('is_substantial', False)

                # Store indices instead of extracting text here
                # The text will be extracted later in process_extracted_statements_data
                speech_start_idx = start_idx
                speech_end_idx = end_idx

                # Clean speaker name from titles
                if speaker_name:
                    titles_to_remove = [
                        '위원장', '부위원장', '의원', '장관', '차관', '의장', '부의장', '의사국장',
                        '사무관', '국장', '서기관', '실장', '청장', '원장', '대변인', '비서관',
                        '수석', '정무위원', '간사'
                    ]

                    for title in titles_to_remove:
                        speaker_name = speaker_name.replace(title, '').strip()

                # --- Attach DB categories/subcategories to result ---
                result = {
                    **analysis_json,
                    'speaker_name': speaker_name,
                    'start_idx': speech_start_idx,
                    'end_idx': speech_end_idx,
                    'segment_index': batch_start_index + i,
                }
                if main_policy_category is not None:
                    result['main_policy_category'] = main_policy_category
                if policy_subcategories:
                    result['policy_subcategories'] = policy_subcategories
                results.append(result)

                # Validate speaker
                is_real_member = speaker_name in assembly_members if assembly_members and speaker_name else is_valid_member

                should_ignore = any(
                    ignored in speaker_name
                    for ignored in IGNORED_SPEAKERS) if speaker_name else True

                if (speaker_name and speech_start_idx is not None
                        and speech_end_idx is not None and is_valid_member
                        and is_substantial and not should_ignore
                        and is_real_member):

                    results.append({
                        'speaker_name':
                        speaker_name,
                        'start_idx':
                        speech_start_idx,
                        'end_idx':
                        speech_end_idx,
                        'sentiment_score':
                        analysis_json.get('sentiment_score', 0.0),
                        'sentiment_reason':
                        'LLM 배치 분석 완료',
                        'bill_relevance_score':
                        analysis_json.get('bill_relevance_score', 0.0),
                        'policy_categories': [],
                        'policy_keywords': [],
                        'bill_specific_keywords': [],
                        'segment_index':
                        batch_start_index + i
                    })

            logger.info(
                f"✅ Batch processed {len(results)} valid statements from {len(cleaned_segments)} segments"
            )
            return results

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e).lower()

            # Determine error type and retry strategy
            is_retryable_error = False
            wait_time = 5  # Default wait time

            if "500" in error_msg and "internal error" in error_msg:
                is_retryable_error = True
                wait_time = 10 + (attempt * 10)  # 10s, 20s, 30s
                logger.error(
                    f"Error in batch analysis after {processing_time:.1f}s: 500 An internal error has occurred. Please retry or report in https://developers.generativeai.google/guide/troubleshooting"
                )
            elif "504" in error_msg or "deadline" in error_msg or "timeout" in error_msg:
                is_retryable_error = True
                wait_time = 15 + (attempt * 15)  # 15s, 30s, 45s
                logger.warning(
                    f"⏰ BATCH TIMEOUT after {processing_time:.1f}s: {e}")
            elif "429" in error_msg or "quota" in error_msg or "rate" in error_msg:
                is_retryable_error = True
                wait_time = 20 + (attempt * 20)  # 20s, 40s, 60s
                logger.warning(f"Rate limit hit during batch analysis: {e}")
            else:
                # Non-retryable error
                logger.error(
                    f"Non-retryable error in batch analysis after {processing_time:.1f}s: {e}"
                )
                return []

            if is_retryable_error and attempt < max_retries:
                logger.info(
                    f"Resting {wait_time}s before retry {attempt + 1}/{max_retries}..."
                )
                time.sleep(wait_time)
                continue
            elif is_retryable_error:
                logger.error(
                    f"Max retries ({max_retries}) exceeded for batch analysis. Final error: {e}"
                )
                return []
            else:
                return []

    return []


# Legacy single statement analysis functions removed - all processing now goes through batch analysis
# to handle rate limits efficiently. Use analyze_speech_segment_with_llm_batch instead.


@with_db_retry
def create_placeholder_bill_from_llm(session_obj, bill_title):
    """Creates a placeholder Bill from a title discovered by the LLM."""
    if not bill_title:
        return None

    # Generate a unique ID based on the title and session
    unique_id = f"LLM_{session_obj.conf_id}_{hash(bill_title)}"

    bill, created = Bill.objects.get_or_create(
        bill_id=unique_id,
        defaults={
            'session': session_obj,
            'bill_nm': bill_title,
            # Let the model's default "정보 없음" handle the proposer field.
            # bill_no will be NULL (if your model allows it).
        })
    if created:
        logger.info(
            f"✨ LLM discovered and created placeholder for: '{bill_title[:60]}...'"
        )
    return bill


@with_db_retry
def update_bill_policy_data(bill_obj, segment_data):
    """Update bill with policy analysis data from segmentation and create database mappings."""
    try:
        from .models import Category, Subcategory, BillCategoryMapping, BillSubcategoryMapping

        # Extract data from segment
        main_policy_category = segment_data.get('main_policy_category', '')
        policy_subcategories = segment_data.get('policy_subcategories', [])
        key_policy_phrases = segment_data.get('key_policy_phrases', [])
        bill_specific_keywords = segment_data.get('bill_specific_keywords', [])
        policy_stance = segment_data.get('policy_stance', 'moderate')
        bill_analysis = segment_data.get('bill_analysis', '')

        # Update bill fields
        bill_obj.policy_categories = [main_policy_category
                                      ] if main_policy_category else []
        bill_obj.key_policy_phrases = key_policy_phrases
        bill_obj.bill_specific_keywords = bill_specific_keywords

        # Create category analysis text
        if main_policy_category:
            category_analysis = f"주요 정책 분야: {main_policy_category}"
            if policy_subcategories:
                category_analysis += f"\n세부 분야: {', '.join(policy_subcategories)}"
            if bill_analysis:
                category_analysis += f"\n분석: {bill_analysis}"
            bill_obj.category_analysis = category_analysis

        # Create policy keywords string
        if key_policy_phrases:
            bill_obj.policy_keywords = ', '.join(key_policy_phrases)

        # Set LLM analysis metadata
        bill_obj.llm_analysis_version = "v1.0"
        bill_obj.llm_confidence_score = 0.8  # Default confidence

        # Calculate policy impact score based on keywords and content
        impact_score = len(key_policy_phrases) * 2 + len(
            bill_specific_keywords)
        bill_obj.policy_impact_score = min(10.0, impact_score)

        bill_obj.save()

        # Create category mappings in database
        if main_policy_category:
            try:
                # Find or create main category
                category_obj = Category.objects.filter(
                    name=main_policy_category).first()
                if category_obj:
                    # Create or update bill-category mapping
                    mapping, created = BillCategoryMapping.objects.update_or_create(
                        bill=bill_obj,
                        category=category_obj,
                        defaults={
                            'confidence_score': 0.8,
                            'is_primary': True,
                            'analysis_method': 'llm_discovery'
                        })

                    # Create subcategory mappings
                    for subcat_name in policy_subcategories:
                        subcategory_obj = Subcategory.objects.filter(
                            category=category_obj, name=subcat_name).first()

                        if subcategory_obj:
                            subcat_mapping, sub_created = BillSubcategoryMapping.objects.update_or_create(
                                bill=bill_obj,
                                subcategory=subcategory_obj,
                                defaults={
                                    'relevance_score':
                                    0.7,
                                    'supporting_evidence':
                                    bill_analysis,
                                    'extracted_keywords':
                                    bill_specific_keywords,
                                    'policy_position':
                                    'support' if policy_stance == 'progressive'
                                    else 'neutral'
                                })
                            if sub_created:
                                logger.info(
                                    f"✅ Created subcategory mapping: {bill_obj.bill_nm[:30]}... -> {subcat_name}"
                                )

                    if created:
                        logger.info(
                            f"✅ Created category mapping: {bill_obj.bill_nm[:30]}... -> {main_policy_category}"
                        )
                else:
                    logger.warning(
                        f"⚠️ Category '{main_policy_category}' not found in database"
                    )

            except Exception as mapping_error:
                logger.error(
                    f"❌ Error creating category mappings: {mapping_error}")

        logger.info(
            f"✅ Updated policy data for bill: {bill_obj.bill_nm[:50]}...")

    except Exception as e:
        logger.error(f"❌ Error updating bill policy data: {e}")
        logger.exception("Full traceback for bill policy update:")


import json
import logging


def _attempt_json_repair(response_text):
    """Attempt to repair common JSON issues in LLM responses."""
    try:
        # Remove any trailing incomplete content after the last complete object
        response_text = response_text.strip()

        # Find the last complete closing brace
        last_brace = response_text.rfind('}')
        if last_brace == -1:
            return None

        # Check if we have proper array closing
        remaining = response_text[last_brace + 1:].strip()
        if remaining and not remaining.startswith(']'):
            # Try to find the last complete array closing
            last_bracket = response_text.rfind(']')
            if last_bracket > last_brace:
                last_brace = last_bracket

        # Truncate to last complete structure
        truncated = response_text[:last_brace + 1]

        # Try to close any unclosed arrays or objects
        open_braces = truncated.count('{') - truncated.count('}')
        open_brackets = truncated.count('[') - truncated.count(']')

        # Add missing closing characters
        for _ in range(open_braces):
            truncated += '}'
        for _ in range(open_brackets):
            truncated += ']'

        # Validate the structure
        json.loads(truncated)
        return truncated

    except Exception as e:
        logger.debug(f"JSON repair attempt failed: {e}")
        return None


def extract_statements_with_llm_discovery(full_text,
                                          session_id,
                                          known_bill_names,
                                          session_obj,
                                          debug=False):

    logger = logging.getLogger(__name__)
    logger.info(
        f"🤖 Starting LLM discovery and segmentation for session: {session_id}")

    if not reinitialize_gemini():
        logger.error("❌ Gemini not available. Cannot perform LLM discovery.")
        return []

    # Load policy categories from code.txt file for enhanced analysis
    policy_categories_from_db = {}
    try:
        logger.info(
            "📁 Loading policy categories from: ../Additional_Files/code.txt")

        code_file_path = Path("../Additional_Files/code.txt")
        if not code_file_path.exists():
            code_file_path = Path("Additional_Files/code.txt")

        if code_file_path.exists():
            with open(code_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Skip header line
            lines = lines[1:] if lines else []

            current_categories = {}
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    parts = line.split(',')
                    if len(parts) >= 4:
                        main_category = parts[0].strip()
                        sub_category = parts[1].strip()
                        main_description = parts[2].strip()

                        if main_category not in current_categories:
                            current_categories[main_category] = {
                                'description': main_description,
                                'subcategories': []
                            }

                        if sub_category and sub_category not in current_categories[
                                main_category]['subcategories']:
                            current_categories[main_category][
                                'subcategories'].append(sub_category)

                except Exception as line_error:
                    logger.warning(
                        f"Error parsing line: {line[:50]}... - {line_error}")
                    continue

            policy_categories_from_db = current_categories

            # Summary logging
            total_categories = len(policy_categories_from_db)
            total_subcategories = sum(
                len(cat['subcategories'])
                for cat in policy_categories_from_db.values())

            logger.info(f"📊 Category Summary:")
            for cat_name, cat_data in policy_categories_from_db.items():
                subcat_count = len(cat_data['subcategories'])
                logger.info(f"  📂 {cat_name}: {subcat_count} subcategories")

        else:
            logger.warning(
                "❌ code.txt file not found, using fallback categories")
            policy_categories_from_db = {}

    except Exception as e:
        logger.warning(f"Could not load policy categories from code.txt: {e}")
        policy_categories_from_db = {}

    # Prepare the list of known bills for the prompt
    if known_bill_names:
        known_bills_str = "\n".join(f"- {name}" for name in known_bill_names)
    else:
        known_bills_str = "No known bills were provided."

    # Create indexed categories for more efficient LLM responses
    if policy_categories_from_db:
        policy_categories_section = "**POLICY CATEGORIES (use index numbers):**\n"
        category_index = 1
        subcategory_index = 1
        category_mapping = {}
        subcategory_mapping = {}

        for cat_name, cat_data in policy_categories_from_db.items():
            policy_categories_section += f"{category_index}. {cat_name}\n"
            category_mapping[category_index] = cat_name

            if cat_data['subcategories']:
                for subcat in cat_data[
                        'subcategories'][:
                                         3]:  # Limit to 3 subcategories for brevity
                    policy_categories_section += f"  {subcategory_index}. {subcat}\n"
                    subcategory_mapping[subcategory_index] = (category_index,
                                                              subcat)
                    subcategory_index += 1

            category_index += 1
    else:
        policy_categories_section = """**POLICY CATEGORIES (use index numbers):**
1. 경제정책
2. 사회정책  
3. 외교안보정책
4. 법행정제도
5. 과학기술정책
6. 문화체육정책
7. 인권소수자정책
8. 지역균형정책
9. 정치정책"""

        # Fallback mapping
        category_mapping = {
            1: "경제정책",
            2: "사회정책",
            3: "외교안보정책",
            4: "법행정제도",
            5: "과학기술정책",
            6: "문화체육정책",
            7: "인권소수자정책",
            8: "지역균형정책",
            9: "정치정책"
        }
        subcategory_mapping = {}

    prompt = f"""You are a world-class legislative analyst AI. Your task is to read a parliamentary transcript
and perfectly segment the entire discussion for all topics, while also analyzing policy content.

**CONTEXT:**
I already know about the following bills. You MUST find the discussion for these if they exist.
--- KNOWN BILLS ---
{known_bills_str}

**YOUR CRITICAL MISSION:**
1. Read the entire transcript below.
2. Identify the exact start and end character index for the complete discussion of each **KNOWN BILL**.
3. Discover any additional bills/topics not in the known list, and identify their discussion spans.
4. For each bill/topic, analyze the policy content and categorize it using the categories below.
5. Return a JSON object with segmentation AND detailed policy analysis.

{policy_categories_section}

**ANALYSIS REQUIREMENTS:**
- For each bill/topic, identify the main policy category and up to 3 subcategories
- Extract 3-7 key policy phrases that represent the core policy elements
- Extract 3-5 bill-specific keywords (technical terms, specific provisions)
- Provide a concise policy analysis (max 80 Korean characters)
- Assess policy stance: progressive/conservative/moderate

**RULES:**
- Ignore any mentions that occur in the table-of-contents or front-matter portion of the document
  (before the Chair officially opens the debate).
- A discussion segment **must** be substantive, containing actual debate or remarks from multiple speakers.
  Do not segment short procedural announcements.
- `bill_name` for known bills MUST EXACTLY MATCH the provided list.
- For new items, create a concise, accurate `bill_name`.
- Use exact category names from the policy categories list above.
- Return **ONLY** the final JSON object.

**TRANSCRIPT:**
---
{full_text}
---

**REQUIRED JSON OUTPUT FORMAT (use category indices):**
{{
  "bills_found": [
    {{
      "bill_name": "Exact name of a KNOWN bill",
      "start_index": 1234,
      "end_index": 5678,
      "category_id": 1,
      "subcategory_ids": [12, 15],
      "keywords": ["키워드1", "키워드2"],
      "stance": "P"
    }}
  ],
  "newly_discovered": [
    {{
      "bill_name": "Name of newly discovered topic",
      "start_index": 2345,
      "end_index": 6789,
      "category_id": 5,
      "subcategory_ids": [23],
      "keywords": ["키워드1", "키워드2"],
      "stance": "C"
    }}
  ]
}}

**FORMAT RULES:**
- Use category_id numbers from the list above
- Use subcategory_ids array (max 3 numbers)
- Max 5 keywords per bill
- stance: "P"=progressive, "C"=conservative, "M"=moderate
"""
    try:
        global client
        if not client:
            logger.error("Gemini client not initialized for LLM discovery.")
            return []

        estimated_tokens = len(prompt) // 3

        if not gemini_rate_limiter.wait_if_needed(estimated_tokens):
            logger.error(
                "Rate limit timeout for LLM discovery. Falling back to keyword extraction."
            )
            return extract_statements_with_keyword_fallback(
                full_text, session_id, debug)

        # Use new google.genai structure with more conservative settings
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="text/plain",
                temperature=0.1,  # Lower temperature for more consistent JSON
                max_output_tokens=8000)
        )  # Reduced since we're using compact format
        gemini_rate_limiter.record_request(estimated_tokens, success=True)

        # Check if response exists and has text
        if not response or not hasattr(response, 'text') or not response.text:
            logger.error(
                "❌ No response or empty response from LLM discovery. Falling back to keyword extraction."
            )
            return extract_statements_with_keyword_fallback(
                full_text, session_id, debug)

        # Strip markdown fences if present
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json",
                                                  "").replace("```",
                                                              "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.split("```", 2)[-1].strip()

        # Print/log the raw LLM response for debugging
        logger.info(
            f"🐛 DEBUG: Raw LLM response length: {len(response_text)} chars")
        logger.info(
            f"🐛 DEBUG: Raw LLM response (first 1000 chars): {response_text[:1000]}"
        )
        if len(response_text) > 1000:
            logger.info(
                f"🐛 DEBUG: Raw LLM response (last 500 chars): {response_text[-500:]}"
            )

        # Check if response is empty or invalid
        if not response_text or len(response_text) < 10:
            logger.error(
                f"❌ Empty or too short response from LLM discovery ({len(response_text)} chars). Falling back to keyword extraction."
            )
            return extract_statements_with_keyword_fallback(
                full_text, session_id, debug)

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as json_err:
            logger.error(f"❌ JSON decode error in LLM discovery: {json_err}")
            logger.error(
                f"Raw response (first 500 chars): {response_text[:500]}...")

            # Try to fix common JSON issues
            fixed_response = _attempt_json_repair(response_text)
            if fixed_response:
                try:
                    data = json.loads(fixed_response)
                    logger.info(
                        "✅ Successfully repaired and parsed JSON response")
                except json.JSONDecodeError:
                    logger.error("❌ JSON repair attempt failed")
                    logger.info("🔄 Falling back to keyword-based extraction.")
                    return extract_statements_with_keyword_fallback(
                        full_text, session_id, debug)
            else:
                logger.info("🔄 Falling back to keyword-based extraction.")
                return extract_statements_with_keyword_fallback(
                    full_text, session_id, debug)
        if not isinstance(data, dict):
            logger.error(
                "LLM discovery did not return a JSON object. Falling back to keyword extraction."
            )
            return extract_statements_with_keyword_fallback(
                full_text, session_id, debug)

        # Validate required structure
        if 'bills_found' not in data and 'newly_discovered' not in data:
            logger.error(
                "LLM discovery response missing required fields. Falling back to keyword extraction."
            )
            return extract_statements_with_keyword_fallback(
                full_text, session_id, debug)

        # Ensure arrays exist
        if 'bills_found' not in data:
            data['bills_found'] = []
        if 'newly_discovered' not in data:
            data['newly_discovered'] = []

        # Resolve category indices back to names and merge segments
        all_segments = []

        for seg in data.get("bills_found", []):
            seg["is_newly_discovered"] = False
            # Resolve category indices to names
            if "category_id" in seg:
                seg["main_policy_category"] = category_mapping.get(
                    seg["category_id"], "기타")
                seg["policy_subcategories"] = []
                for sub_id in seg.get("subcategory_ids", []):
                    if sub_id in subcategory_mapping:
                        seg["policy_subcategories"].append(
                            subcategory_mapping[sub_id][1])

            # Convert compact format to full format
            seg["key_policy_phrases"] = seg.get("keywords", [])
            seg["bill_specific_keywords"] = seg.get(
                "keywords", [])[:3]  # First 3 as specific
            stance_map = {
                "P": "progressive",
                "C": "conservative",
                "M": "moderate"
            }
            seg["policy_stance"] = stance_map.get(seg.get("stance", "M"),
                                                  "moderate")
            seg["bill_analysis"] = f"{seg.get('bill_name', '')} 관련 정책"

            all_segments.append(seg)

        for seg in data.get("newly_discovered", []):
            seg["is_newly_discovered"] = True
            # Resolve category indices to names
            if "category_id" in seg:
                seg["main_policy_category"] = category_mapping.get(
                    seg["category_id"], "기타")
                seg["policy_subcategories"] = []
                for sub_id in seg.get("subcategory_ids", []):
                    if sub_id in subcategory_mapping:
                        seg["policy_subcategories"].append(
                            subcategory_mapping[sub_id][1])

            # Convert compact format to full format
            seg["key_policy_phrases"] = seg.get("keywords", [])
            seg["bill_specific_keywords"] = seg.get("keywords", [])[:3]
            stance_map = {
                "P": "progressive",
                "C": "conservative",
                "M": "moderate"
            }
            seg["policy_stance"] = stance_map.get(seg.get("stance", "M"),
                                                  "moderate")
            seg["bill_analysis"] = f"{seg.get('bill_name', '')} 관련 정책"

            all_segments.append(seg)

        logger.info(
            f"✅ LLM segmented {len(all_segments)} total discussion topics.")

        # Create placeholders for newly discovered bills with policy analysis
        if not debug:
            for segment in all_segments:
                if segment.get("is_newly_discovered"):
                    bill_obj = create_placeholder_bill_from_llm(
                        session_obj, segment["bill_name"])
                    # Update bill with policy analysis from segmentation
                    if bill_obj:
                        update_bill_policy_data(bill_obj, segment)

        # Process each segment to extract statements and update policy data
        all_statements = []
        for segment in sorted(all_segments,
                              key=lambda x: x.get('start_index', 0)):
            bill_name = segment.get("bill_name")
            start = segment.get("start_index", 0)
            end = segment.get("end_index", 0)

            # Validate segment data
            if not bill_name or end <= start:
                logger.warning(
                    f"Invalid segment data: bill_name='{bill_name}', start={start}, end={end}"
                )
                continue

            # Ensure indices are within text bounds
            start = max(0, min(start, len(full_text)))
            end = max(start, min(end, len(full_text)))

            if end - start < 50:  # Skip very short segments
                logger.warning(
                    f"Skipping very short segment for bill '{bill_name}': {end - start} chars"
                )
                continue

            # Update policy data for known bills as well
            if not debug and not segment.get("is_newly_discovered"):
                try:
                    # Find the existing bill and update its policy data
                    existing_bill = Bill.objects.filter(
                        session=session_obj,
                        bill_nm__iexact=bill_name).first()
                    if existing_bill:
                        update_bill_policy_data(existing_bill, segment)
                except Exception as e:
                    logger.error(
                        f"Could not update policy data for known bill '{bill_name}': {e}"
                    )

            segment_text = full_text[start:end]

            statements_in_segment = extract_statements_for_bill_segment(
                segment_text, session_id, bill_name, debug)

            # Associate these statements with the correct bill name and policy data
            for stmt in statements_in_segment:
                stmt['associated_bill_name'] = bill_name
                # Add policy context to statements
                stmt['policy_categories'] = segment.get(
                    'policy_categories', [])
                stmt['policy_keywords'] = segment.get('key_policy_phrases', [])
                stmt['bill_specific_keywords'] = segment.get(
                    'bill_specific_keywords', [])

            all_statements.extend(statements_in_segment)

        return all_statements

    except Exception as e:
        gemini_rate_limiter.record_error("llm_discovery_error")
        logger.error(
            f"❌ Critical error during LLM discovery and segmentation: {e}")
        logger.exception("Full traceback for LLM discovery:")
        logger.info(
            "🔄 Falling back to keyword-based extraction due to LLM error.")
        return extract_statements_with_keyword_fallback(
            full_text, session_id, debug)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
# In tasks.py, replace the existing process_session_pdf function

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self=None, session_id=None, force=False, debug=False):
    """Download, parse PDF transcript for a session, and extract statements."""
    if not session_id:
        logger.error("session_id is required for process_session_pdf.")
        return

    logger.info(
        f"📄 Processing PDF for session: {session_id} (force={force}, debug={debug})"
    )

    try:
        session = Session.objects.get(conf_id=session_id)
    except Session.DoesNotExist:
        logger.error(
            f"❌ Session {session_id} not found in DB. Cannot process PDF.")
        return

    if not session.down_url:
        logger.info(
            f"ℹ️ No PDF URL for session {session_id}. Skipping PDF processing."
        )
        return

    if Statement.objects.filter(
            session=session).exists() and not force and not debug:
        logger.info(
            f"Statements already exist for session {session_id} and not in force/debug mode. Skipping."
        )
        return

    if debug:
        logger.debug(f"🐛 DEBUG: Simulating PDF processing for {session_id}.")
        return

    temp_pdf_path = None
    try:
        logger.info(f"📥 Downloading PDF from: {session.down_url}")
        response = requests.get(session.down_url, timeout=120, stream=True)
        response.raise_for_status()

        temp_dir = Path(getattr(settings, "TEMP_FILE_DIR", "temp_files"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_pdf_path = temp_dir / f"session_{session_id}_{int(time.time())}.pdf"

        with open(temp_pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(
            f"📥 PDF for session {session_id} downloaded to {temp_pdf_path}")

        full_text = ""
        with pdfplumber.open(temp_pdf_path) as pdf:
            pages = pdf.pages
            logger.info(f"Extracting text from {len(pages)} pages...")
            for i, page in enumerate(pages):
                page_text = page.extract_text(x_tolerance=1, y_tolerance=3)
                if page_text:
                    full_text += page_text + "\n"
                if (i + 1) % 20 == 0:
                    logger.info(f"Processed {i+1}/{len(pages)} pages...")
        logger.info(f"📄 Extracted ~{len(full_text)} chars from PDF.")

        if not full_text.strip():
            logger.warning(
                f"Extracted text is empty for session {session_id}.")
            return

        # --- KEY FIX: Fetch the list of bills from the database ---
        bills_for_session = get_session_bill_names(session_id)

        # This is where the main logic is called.
        process_pdf_text_for_statements(
            full_text,
            session_id,
            session,
            None,  # bills_context_str is no longer needed
            bills_for_session,  # Pass the list of bills from the DB
            debug)

    except RequestException as re_exc:
        logger.error(
            f"Request error downloading PDF for session {session_id}: {re_exc}"
        )
        if self:
            self.retry(exc=re_exc)
    except Exception as e:
        logger.error(
            f"❌ Unexpected error processing PDF for session {session_id}: {e}")
        logger.exception(f"Full traceback for PDF processing {session_id}:")
        if self:
            self.retry(exc=e)
    finally:
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.info(f"🗑️ Deleted temporary PDF: {temp_pdf_path}")
            except OSError as e_del:
                logger.error(
                    f"Error deleting temporary PDF {temp_pdf_path}: {e_del}")


def process_extracted_statements_data(statements_data_list,
                                      session_obj,
                                      full_text,
                                      debug=False):
    """Saves a list of processed statement data (dictionaries) to the database.
    Now accepts start/end indices and extracts text locally."""
    if debug:
        logger.debug(
            f"🐛 DEBUG: Would process {len(statements_data_list)} statement data items. Not saving to DB."
        )
        return

    if not statements_data_list:
        logger.info(
            f"No statement data to save for session {session_obj.conf_id}.")
        return

    @with_db_retry
    def _check_statement_exists(session_obj, speaker_obj, statement_text):
        return Statement.objects.filter(session=session_obj,
                                        speaker=speaker_obj,
                                        text_hash=Statement.calculate_hash(
                                            statement_text,
                                            speaker_obj.naas_cd,
                                            session_obj.conf_id)).exists()

    @with_db_retry
    def _find_bill_for_statement(session_obj, assoc_bill_name_from_data):
        associated_bill_obj = Bill.objects.filter(
            session=session_obj,
            bill_nm__iexact=assoc_bill_name_from_data).first()
        if not associated_bill_obj:
            bill_candidates = Bill.objects.filter(
                session=session_obj,
                bill_nm__icontains=assoc_bill_name_from_data.split(
                    '(')[0].strip())
            if bill_candidates.count() == 1:
                associated_bill_obj = bill_candidates.first()
        return associated_bill_obj

    @with_db_retry
    def _save_statement(new_statement):
        new_statement.save()
        return new_statement

    def _is_valid_statement_content(text):
        """Validate that extracted text is actual statement content, not headers/metadata."""
        if not text or len(text) < 20:
            return False

        # Check for header patterns that indicate this is not actual speech
        invalid_patterns = [
            r'^제\d+회-제\d+차',  # Session headers
            r'^국\s*회\s*본\s*회\s*의\s*회\s*의\s*록',  # Meeting record headers
            r'^\d{1,4}\s*$',  # Just page numbers
            r'^회의록\s*$',  # Just "record" label
            r'^국회사무처',  # Administrative text
        ]

        for pattern in invalid_patterns:
            if re.match(pattern, text.strip(), re.IGNORECASE):
                return False

        # Must contain speaker marker or be substantial content
        if not ('◯' in text or len(text) > 100):
            return False

        return True

    created_count = 0
    skipped_invalid_count = 0
    logger.info(
        f"Attempting to save {len(statements_data_list)} statements for session {session_obj.conf_id}."
    )
    for stmt_data in statements_data_list:
        try:
            speaker_name = stmt_data.get('speaker_name', '').strip()

            # Extract text using start/end indices if provided, otherwise use 'text' field
            start_idx = stmt_data.get('start_idx')
            end_idx = stmt_data.get('end_idx')

            if start_idx is not None and end_idx is not None and full_text:
                # Extract text locally using indices
                start_idx = max(0, min(start_idx, len(full_text)))
                end_idx = max(start_idx, min(end_idx, len(full_text)))
                statement_text = full_text[start_idx:end_idx].strip()
                logger.debug(
                    f"Extracted text from indices [{start_idx}:{end_idx}]: {len(statement_text)} chars"
                )
            else:
                # Fallback to provided text field
                statement_text = stmt_data.get('text', '').strip()

            # Validate statement content
            if not _is_valid_statement_content(statement_text):
                logger.debug(
                    f"Skipping invalid statement content: {statement_text[:100]}..."
                )
                skipped_invalid_count += 1
                continue

            if not speaker_name or not statement_text:
                logger.warning(
                    f"Skipping statement with missing speaker ('{speaker_name}') or text for session {session_obj.conf_id}."
                )
                continue

            speaker_obj = get_or_create_speaker(
                speaker_name,
                debug=debug)  # Debug here should match overall debug
            if not speaker_obj:
                logger.warning(
                    f"⚠️ Could not get/create speaker: {speaker_name}. Skipping statement."
                )
                continue

            # Check for existing identical statement (text, speaker, session) to avoid duplicates from reprocessing
            if _check_statement_exists(session_obj, speaker_obj,
                                       statement_text):
                logger.info(
                    f"ℹ️ Identical statement by {speaker_name} (hash match) already exists for session {session_obj.conf_id}. Skipping."
                )
                continue

            associated_bill_obj = None
            assoc_bill_name_from_data = stmt_data.get(
                'associated_bill_name'
            )  # Set during segmentation/full_text processing
            if assoc_bill_name_from_data and assoc_bill_name_from_data not in [
                    "General Discussion / Full Transcript",
                    "Unknown Bill Segment", "General Discussion"
            ]:
                # Try to find the Bill object with improved matching
                try:
                    # First try exact match
                    associated_bill_obj = Bill.objects.filter(
                        session=session_obj,
                        bill_nm__iexact=assoc_bill_name_from_data).first()

                    if not associated_bill_obj:
                        # Try partial match by removing common suffixes/prefixes
                        clean_name = assoc_bill_name_from_data.split(
                            '(')[0].strip()
                        clean_name = clean_name.replace('의안', '').replace(
                            '법률안', '').strip()

                        # Try contains match
                        bill_candidates = Bill.objects.filter(
                            session=session_obj, bill_nm__icontains=clean_name)

                        if bill_candidates.count() == 1:
                            associated_bill_obj = bill_candidates.first()
                            logger.info(
                                f"✅ Found bill match via partial matching: '{assoc_bill_name_from_data}' -> '{associated_bill_obj.bill_nm}'"
                            )
                        elif bill_candidates.count() > 1:
                            # Try to find best match by similarity
                            best_match = None
                            best_score = 0
                            for candidate in bill_candidates:
                                # Simple similarity check - count common words
                                data_words = set(
                                    assoc_bill_name_from_data.lower().split())
                                candidate_words = set(
                                    candidate.bill_nm.lower().split())
                                common_words = len(
                                    data_words.intersection(candidate_words))
                                total_words = len(
                                    data_words.union(candidate_words))
                                similarity = common_words / total_words if total_words > 0 else 0

                                if similarity > best_score and similarity > 0.5:  # At least 50% similarity
                                    best_score = similarity
                                    best_match = candidate

                            if best_match:
                                associated_bill_obj = best_match
                                logger.info(
                                    f"✅ Found best bill match (similarity: {best_score:.2f}): '{assoc_bill_name_from_data}' -> '{associated_bill_obj.bill_nm}'"
                                )
                            else:
                                logger.warning(
                                    f"Multiple ambiguous bill matches for '{assoc_bill_name_from_data}' in session {session_obj.conf_id}. Not associating."
                                )
                    else:
                        logger.info(
                            f"✅ Found exact bill match: '{assoc_bill_name_from_data}'"
                        )

                except Exception as e_bill_find:
                    logger.warning(
                        f"⚠️ Error finding bill '{assoc_bill_name_from_data}' for statement: {e_bill_find}"
                    )

            # Construct statement model instance
            new_statement = Statement(
                session=session_obj,
                bill=associated_bill_obj,
                speaker=speaker_obj,
                text=statement_text,
                sentiment_score=stmt_data.get('sentiment_score', 0.0),
                sentiment_reason=stmt_data.get('sentiment_reason',
                                               'Analysis not fully run'),
                bill_relevance_score=stmt_data.get('bill_relevance_score',
                                                   0.0))
            new_statement = _save_statement(
                new_statement
            )  # This also calculates and saves text_hash via pre_save signal
            created_count += 1

            bill_info_log = f" (Bill: {associated_bill_obj.bill_nm[:20]}...)" if associated_bill_obj else f" (Assoc. Bill Name: {assoc_bill_name_from_data[:20]})" if assoc_bill_name_from_data else ""
            logger.info(
                f"✨ Created statement ({new_statement.id}) for {speaker_name}{bill_info_log}: {statement_text[:40]}..."
            )

            if stmt_data.get('policy_categories'):
                create_statement_categories(new_statement,
                                            stmt_data['policy_categories'])

        except Exception as e_stmt_save:
            logger.error(
                f"❌ Error creating statement object in DB: {e_stmt_save} for speaker {stmt_data.get('speaker_name', 'N/A')}"
            )
            logger.error(
                f"Failing statement data: {json.dumps(stmt_data, ensure_ascii=False, indent=2)}"
            )
            logger.exception("Traceback for statement save error:")
            continue  # Continue with the next statement

    logger.info(
        f"🎉 Saved {created_count} new statements for session {session_obj.conf_id}. Skipped {skipped_invalid_count} invalid content items."
    )


def extract_statements_with_keyword_fallback(text, session_id, debug=False):
    """
    Extract statements using keyword patterns when LLM fails.
    Looks for common bill discussion markers and speaker patterns.
    """
    if not text:
        return []

    logger.info(
        f"🔍 Using keyword-based fallback extraction for session {session_id}")

    # Procedural text patterns to ignore (these are not bills)
    procedural_patterns = [
        r'의장\s+\w+',  # "의장 우원식" etc.
        r'의사일정\s+제\d+항',  # "의사일정 제1항" etc.
        r'국회본회의\s+회의록',  # Meeting records
        r'제\d+회-제\d+차',  # Session numbers
        r'개의|산회|폐회',  # Opening/closing session words
    ]

    def is_procedural_text(text_to_check):
        """Check if text is procedural rather than a bill name"""
        for pattern in procedural_patterns:
            if re.search(pattern, text_to_check):
                return True
        return False

    # Find bill discussion sections using improved patterns
    bill_patterns = [
        r'(?:^|\n)\s*(\d+)\.\s*([^○\n]{15,150}법률안[^○\n]*)',  # "번호. ...법률안" pattern
        r'의안번호\s*(\d+)[^○]*?([^○\n]{10,80}법률안[^○\n]*)',  # "의안번호 XXXX ...법률안" pattern
        r'(?:^|\n)\s*(\d+)\.\s*([^○\n]{15,150}(?:특별검사|특검)[^○\n]*)',  # Special prosecutor bills
    ]

    bill_segments = []
    for pattern in bill_patterns:
        matches = list(re.finditer(pattern, text, re.DOTALL | re.MULTILINE))
        for match in matches:
            start_pos = match.start()
            bill_name = match.group(2).strip() if len(
                match.groups()) > 1 else match.group(1).strip()

            # Filter out procedural text and very short names
            if (len(bill_name) > 15 and not is_procedural_text(bill_name)
                    and ('법률안' in bill_name or '특별검사' in bill_name
                         or '특검' in bill_name)):

                # Clean up the bill name
                bill_name = re.sub(r'^[\d\.\s]+', '',
                                   bill_name)  # Remove leading numbers
                bill_name = bill_name.strip()

                if len(bill_name) > 10:  # Final length check
                    bill_segments.append({
                        'start_pos': start_pos,
                        'bill_name': bill_name[:100]  # Limit length
                    })

    # Sort by position and remove overlaps
    bill_segments.sort(key=lambda x: x['start_pos'])

    # Remove duplicate or very similar bill names
    unique_segments = []
    seen_names = set()
    for segment in bill_segments:
        bill_name_key = segment['bill_name'][:50].lower(
        )  # Use first 50 chars for comparison
        if bill_name_key not in seen_names:
            seen_names.add(bill_name_key)
            unique_segments.append(segment)

    all_statements = []

    if unique_segments:
        logger.info(
            f"Found {len(unique_segments)} valid bill sections using keywords (filtered from {len(bill_segments)} candidates)"
        )

        for i, segment in enumerate(unique_segments):
            start_pos = segment['start_pos']
            end_pos = unique_segments[i + 1]['start_pos'] if i + 1 < len(
                unique_segments) else len(text)

            segment_text = text[start_pos:end_pos]
            bill_name = segment['bill_name']

            # Extract statements from this segment
            statements_in_segment = process_single_segment_for_statements_with_splitting(
                segment_text, session_id, bill_name, debug)

            for stmt_data in statements_in_segment:
                stmt_data['associated_bill_name'] = bill_name

            all_statements.extend(statements_in_segment)
    else:
        # Process entire text as one segment with improved splitting
        logger.info(
            "No valid bill patterns found, processing with general discussion approach"
        )

        # Try to find at least the discussion sections with ◯ markers
        if '◯' in text:
            statements_from_full = process_single_segment_for_statements_with_splitting(
                text, session_id, "General Discussion", debug)

            for stmt_data in statements_from_full:
                stmt_data['associated_bill_name'] = "General Discussion"

            all_statements.extend(statements_from_full)
        else:
            logger.warning(
                f"No ◯ markers found in text for session {session_id}, cannot extract statements"
            )

    logger.info(
        f"✅ Keyword-based extraction completed: {len(all_statements)} statements"
    )
    return all_statements


def extract_statements_with_regex_fallback(text, session_id, debug=False):
    import re
    logger.warning(
        f"⚠️ Using basic regex fallback for statement extraction (session: {session_id}). Results will be very rough."
    )

    cleaned_text = re.sub(r'\n+', '\n', text).replace('\r', '')

    statements = []
    current_speaker = None
    current_speech_lines = []

    for line in cleaned_text.split('\n'):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        if line_stripped.startswith("◯"):
            if current_speaker and current_speech_lines:  # Save previous speaker's utterance
                statements.append({
                    'speaker_name':
                    current_speaker,
                    'text':
                    " ".join(current_speech_lines).strip(),
                    # No LLM analysis in this fallback
                    'sentiment_score':
                    0.0,
                    'sentiment_reason':
                    'Regex Fallback',
                    'policy_categories': [],
                    'policy_keywords': []
                })
                current_speech_lines = []

            # Try to parse new speaker
            speaker_part = line_stripped[1:].split(' ')[
                0]  # Very naive speaker extraction
            # Basic cleanup of common titles if appended without space
            for title in ["의원", "위원장", "장관", "의장"]:
                if speaker_part.endswith(title):
                    speaker_part = speaker_part[:-len(title)]
            current_speaker = speaker_part.strip()

            # Text after speaker name on the same line
            # This logic needs to be much more robust if used seriously
            speech_on_line = " ".join(line_stripped[1:].split(' ')[1:]).strip()
            if speech_on_line:
                current_speech_lines.append(speech_on_line)
        elif current_speaker:  # Line belongs to current speaker
            current_speech_lines.append(line_stripped)

    # Save the last speaker's utterance
    if current_speaker and current_speech_lines:
        statements.append({
            'speaker_name': current_speaker,
            'text': " ".join(current_speech_lines).strip(),
            'sentiment_score': 0.0,
            'sentiment_reason': 'Regex Fallback',
            'policy_categories': [],
            'policy_keywords': []
        })

    logger.info(
        f"Regex fallback completed: Extracted {len(statements)} potential statement blocks for session {session_id}."
    )
    if debug and statements:
        logger.debug(f"Sample regex statement: {statements[0]}")
    return statements


# analyze_single_statement function removed - all analysis now goes through batch processing
# to efficiently handle rate limits and improve performance


def get_bills_context(session_id):
    """Fetch bill names for a session to provide context to LLM. Uses DB."""
    try:
        # This function should call get_session_bill_names which reads from DB
        bill_names = get_session_bill_names(session_id)
        if bill_names:
            return ", ".join(bill_names)
        return "논의된 의안 목록 정보 없음"
    except Exception as e:
        logger.error(
            f"❌ Error fetching bills context string for session {session_id}: {e}"
        )
        return "의안 목록 조회 중 오류 발생"


def create_statement_categories(statement_obj,
                                policy_categories_list_from_llm):
    '''Create/update Category, Subcategory, and StatementCategory associations for a Statement.'''
    if not statement_obj or not policy_categories_list_from_llm:
        return

    from .models import Category, Subcategory, StatementCategory  # Ensure models are importable

    @with_db_retry
    def _get_or_create_category(main_cat_name):
        return Category.objects.get_or_create(
            name=main_cat_name,
            defaults={'description': f'{main_cat_name} 관련 정책'})

    @with_db_retry
    def _get_or_create_subcategory(sub_cat_name, category_obj, main_cat_name):
        return Subcategory.objects.get_or_create(
            name=sub_cat_name,
            category=category_obj,
            defaults={
                'description': f'{sub_cat_name} 관련 세부 정책 ({main_cat_name})'
            })

    @with_db_retry
    def _update_or_create_statement_category(statement_obj, category_obj,
                                             subcategory_obj, confidence):
        return StatementCategory.objects.update_or_create(
            statement=statement_obj,
            category=category_obj,
            subcategory=subcategory_obj,
            defaults={'confidence_score': confidence})

    # Clear existing categories for this statement to repopulate, or implement update logic
    # StatementCategory.objects.filter(statement=statement_obj).delete() # Simple way: delete and recreate

    processed_categories_for_statement = set()

    for cat_data in policy_categories_list_from_llm:
        main_cat_name = cat_data.get('main_category', '').strip()
        sub_cat_name = cat_data.get('sub_category', '').strip()
        confidence = float(cat_data.get('confidence',
                                        0.5))  # Default confidence

        if not main_cat_name:
            continue

        # Avoid duplicate (Main, Sub) for the same statement
        category_tuple = (main_cat_name,
                          sub_cat_name if sub_cat_name else "일반")
        if category_tuple in processed_categories_for_statement:
            continue
        processed_categories_for_statement.add(category_tuple)

        try:
            category_obj, _ = _get_or_create_category(main_cat_name)

            subcategory_obj = None
            if sub_cat_name and sub_cat_name.lower(
            ) != '일반' and sub_cat_name.lower() != '없음':
                subcategory_obj, _ = _get_or_create_subcategory(
                    sub_cat_name, category_obj, main_cat_name)

            # Create or update StatementCategory link
            _update_or_create_statement_category(statement_obj, category_obj,
                                                 subcategory_obj, confidence)
        except Exception as e_cat_create:
            logger.error(
                f"Error creating category links for statement {statement_obj.id} (Cat: {main_cat_name}/{sub_cat_name}): {e_cat_create}"
            )
            continue
    logger.info(
        f"Updated category associations for statement {statement_obj.id}.")


def get_or_create_speaker(speaker_name_raw, debug=False):
    '''Get or create speaker. Relies on `fetch_speaker_details` for new speakers.'''
    if not speaker_name_raw or not speaker_name_raw.strip():
        logger.warning(
            "Empty speaker_name_raw provided to get_or_create_speaker.")
        return None

    speaker_name_cleaned = speaker_name_raw.strip()
    if not speaker_name_cleaned:
        logger.warning(
            f"Speaker name '{speaker_name_raw}' became empty after cleaning.")
        return None

    @with_db_retry
    def _find_existing_speaker():
        return Speaker.objects.filter(naas_nm=speaker_name_cleaned).first()

    @with_db_retry
    def _create_fallback_speaker():
        temp_naas_cd = f"TEMP_{speaker_name_cleaned.replace(' ', '_')}_{int(time.time())}"
        speaker_obj, created = Speaker.objects.get_or_create(
            naas_nm=speaker_name_cleaned,
            defaults={
                'naas_cd': temp_naas_cd,
                'naas_ch_nm': '',
                'plpt_nm': '정보없음',
                'elecd_nm': '',
                'elecd_div_nm': '',
                'cmit_nm': '',
                'blng_cmit_nm': '',
                'rlct_div_nm': '',
                'gtelt_eraco': '',
                'ntr_div': '',
                'naas_pic': ''
            })
        return speaker_obj, created

    try:
        # Try to find by exact cleaned name first
        speaker_obj = _find_existing_speaker()
        if speaker_obj:
            if debug:
                logger.debug(f"Found existing speaker: {speaker_name_cleaned}")
            return speaker_obj

        # If not found, attempt to fetch full details from API.
        logger.info(
            f"Speaker '{speaker_name_cleaned}' not found in DB. Attempting to fetch details from API."
        )
        if not debug:
            speaker_obj_from_api = fetch_speaker_details(speaker_name_cleaned)
            if speaker_obj_from_api:
                logger.info(
                    f"Successfully fetched/created speaker from API: {speaker_obj_from_api.naas_nm}"
                )
                return speaker_obj_from_api
            else:
                logger.warning(
                    f"Failed to fetch details for new speaker '{speaker_name_cleaned}' from API."
                )

        # Finally, use the retry-wrapped fallback creation
        speaker_obj, created = _create_fallback_speaker()
        if created:
            logger.info(
                f"Created basic/temporary speaker record for: {speaker_name_cleaned} (ID: {speaker_obj.naas_cd})."
            )
        else:
            logger.info(
                f"Found speaker {speaker_name_cleaned} via get_or_create after API attempt."
            )
        return speaker_obj

    except Exception as e:
        logger.error(
            f"❌ Error in get_or_create_speaker for '{speaker_name_raw}' after retries: {e}"
        )
        logger.exception("Full traceback for get_or_create_speaker error:")
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_bill_detail_info(self, bill_id, force=False, debug=False):
    '''Fetch detailed bill information using BILLINFODETAIL API.'''
    logger.info(
        f"📄 Fetching detailed info for bill: {bill_id} (force={force}, debug={debug})"
    )

    if debug:
        logger.debug(f"🐛 DEBUG: Skipping bill detail fetch for bill {bill_id}")
        return

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                "ASSEMBLY_API_KEY not configured for bill detail fetch.")
            return

        # Get the bill object
        try:
            bill = Bill.objects.get(bill_id=bill_id)
        except Bill.DoesNotExist:
            logger.error(f"Bill {bill_id} not found in database.")
            return

        # Generate the bill link URL
        bill_link_url = f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}"

        url = "https://open.assembly.go.kr/portal/openapi/BILLINFODETAIL"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "BILL_ID": bill_id,
            "Type": "json"
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if debug:
            logger.debug(
                f"🐛 DEBUG: Bill detail API response for {bill_id}: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        bill_detail_data = None
        api_key_name = 'BILLINFODETAIL'
        if data and api_key_name in data and isinstance(
                data[api_key_name], list):
            if len(data[api_key_name]) > 1 and isinstance(
                    data[api_key_name][1], dict):
                rows = data[api_key_name][1].get('row', [])
                if rows:
                    bill_detail_data = rows[0]  # Take first row
            elif len(data[api_key_name]) > 0 and isinstance(
                    data[api_key_name][0], dict):
                head_info = data[api_key_name][0].get('head')
                if head_info and head_info[0].get('RESULT', {}).get(
                        'CODE', '').startswith("INFO-200"):
                    logger.info(
                        f"API result for bill detail ({bill_id}) indicates no data."
                    )
                elif 'row' in data[api_key_name][0]:
                    rows = data[api_key_name][0].get('row', [])
                    if rows:
                        bill_detail_data = rows[0]

        if not bill_detail_data:
            logger.info(f"No detailed information found for bill {bill_id}")
            return

        # Update bill with detailed information
        updated_fields = []

        # Update bill link URL
        if bill.link_url != bill_link_url:
            bill.link_url = bill_link_url
            updated_fields.append('link_url')

        # Update bill number if not set or different
        if bill_detail_data.get(
                'BILL_NO') and bill.bill_no != bill_detail_data.get('BILL_NO'):
            bill.bill_no = bill_detail_data.get('BILL_NO')
            updated_fields.append('bill_no')

        # Always update proposer information with detailed data from BILLINFODETAIL
        proposer_kind = bill_detail_data.get('PPSR_KIND', '').strip()
        proposer_name = bill_detail_data.get('PPSR', '').strip()

        if proposer_name:
            # Replace generic proposers with real proposer data
            current_proposer = bill.proposer
            is_generic_proposer = current_proposer in [
                '국회본회의', '국회', '본회의'
            ] or any(generic in current_proposer
                     for generic in ['국회본회의', '국회', '본회의'])

            if proposer_kind == '의원' and proposer_name:
                # Individual member proposer - get detailed info
                detailed_proposer = f"{proposer_name}"
                # Try to get party information
                if '등' in proposer_name:
                    # Multiple proposers (e.g., "박성민의원 등 11인")
                    detailed_proposer = proposer_name
                else:
                    # Single proposer - try to get party info
                    speaker_details = fetch_speaker_details(
                        proposer_name.replace('의원', '').strip())
                    if speaker_details and speaker_details.plpt_nm:
                        party_info = speaker_details.plpt_nm.split(
                            '/')[-1].strip()
                        detailed_proposer = f"{proposer_name} ({party_info})"
                    else:
                        detailed_proposer = proposer_name
            elif proposer_kind and proposer_name:
                # Other types of proposers (정부, 위원회 등)
                detailed_proposer = f"{proposer_name} ({proposer_kind})"
            else:
                detailed_proposer = proposer_name

            # Always update if we have better proposer data or if current is generic
            if is_generic_proposer or bill.proposer != detailed_proposer:
                old_proposer = bill.proposer
                bill.proposer = detailed_proposer
                updated_fields.append('proposer')
                if is_generic_proposer:
                    logger.info(
                        f"🔄 Replaced generic proposer '{old_proposer}' with real data: '{detailed_proposer}'"
                    )
                else:
                    logger.info(
                        f"🔄 Updated proposer from '{old_proposer}' to '{detailed_proposer}'"
                    )

        # Update proposal date if available
        if bill_detail_data.get(
                'PPSL_DT') and bill.propose_dt != bill_detail_data.get(
                    'PPSL_DT'):
            bill.propose_dt = bill_detail_data.get('PPSL_DT')
            updated_fields.append('propose_dt')

        # Save if any fields were updated
        if updated_fields or force:
            bill.save()
            logger.info(
                f"✅ Updated bill {bill_id} with detailed info. Fields updated: {', '.join(updated_fields) if updated_fields else 'forced update'}"
            )

            # Log the detailed information
            logger.info(f"📋 Bill Details:")
            logger.info(
                f"   - Bill Name: {bill_detail_data.get('BILL_NM', 'N/A')}")
            logger.info(
                f"   - Bill Number: {bill_detail_data.get('BILL_NO', 'N/A')}")
            logger.info(
                f"   - Proposer Kind: {bill_detail_data.get('PPSR_KIND', 'N/A')}"
            )
            logger.info(
                f"   - Proposer: {bill_detail_data.get('PPSR', 'N/A')}")
            logger.info(
                f"   - Proposal Date: {bill_detail_data.get('PPSL_DT', 'N/A')}"
            )
            logger.info(
                f"   - Session: {bill_detail_data.get('PPSL_SESS', 'N/A')}")
            logger.info(
                f"   - Committee: {bill_detail_data.get('JRCMIT_NM', 'N/A')}")
        else:
            logger.info(f"ℹ️ No updates needed for bill {bill_id}")

        # Optionally fetch voting data for this bill
        if not debug and ENABLE_VOTING_DATA_COLLECTION:
            logger.info(f"🔄 Triggering voting data fetch for bill {bill_id}")
            if is_celery_available():
                fetch_voting_data_for_bill.delay(bill_id,
                                                 force=force,
                                                 debug=debug)
            else:
                fetch_voting_data_for_bill(bill_id, force=force, debug=debug)
        elif not ENABLE_VOTING_DATA_COLLECTION:
            logger.info(
                f"⏸️ Skipping voting data fetch for bill {bill_id} (voting data collection disabled)"
            )

    except RequestException as re_exc:
        logger.error(
            f"Request error fetching bill detail for {bill_id}: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for bill detail {bill_id}.")
    except json.JSONDecodeError as json_e:
        logger.error(f"JSON decode error for bill detail {bill_id}: {json_e}")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching bill detail for {bill_id}: {e}")
        logger.exception(f"Full traceback for bill detail {bill_id}:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected error for bill detail {bill_id}."
            )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_voting_data_for_bill(self, bill_id, force=False, debug=False):
    '''Fetch voting data for a specific bill using nojepdqqaweusdfbi API.'''

    if not ENABLE_VOTING_DATA_COLLECTION:
        logger.info(
            f"⏸️ Skipping voting data collection for bill {bill_id} (disabled by configuration)"
        )
        return

    logger.info(
        f"🗳️ Fetching voting data for bill: {bill_id} (force={force}, debug={debug})"
    )

    if debug:
        logger.debug(f"🐛 DEBUG: Skipping voting data fetch for bill {bill_id}")
        return

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                "ASSEMBLY_API_KEY not configured for voting data fetch.")
            return

        # Get the bill object
        try:
            bill = Bill.objects.get(bill_id=bill_id)
        except Bill.DoesNotExist:
            logger.error(f"Bill {bill_id} not found in database.")
            return

        url = "https://open.assembly.go.kr/portal/openapi/nojepdqqaweusdfbi"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "AGE": "22",
            "BILL_ID": bill_id,
            "Type": "json",
            "pSize": 300
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if debug:
            logger.debug(
                f"🐛 DEBUG: Voting API response for {bill_id}: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        voting_data = []
        api_key_name = 'nojepdqqaweusdfbi'
        if data and api_key_name in data and isinstance(
                data[api_key_name], list):
            if len(data[api_key_name]) > 1 and isinstance(
                    data[api_key_name][1], dict):
                voting_data = data[api_key_name][1].get('row', [])
            elif len(data[api_key_name]) > 0 and isinstance(
                    data[api_key_name][0], dict):
                head_info = data[api_key_name][0].get('head')
                if head_info and head_info[0].get('RESULT', {}).get(
                        'CODE', '').startswith("INFO-200"):
                    logger.info(
                        f"API result for voting data ({bill_id}) indicates no data."
                    )
                elif 'row' in data[api_key_name][0]:
                    voting_data = data[api_key_name][0].get('row', [])

        if not voting_data:
            logger.info(f"No voting data found for bill {bill_id}")
            return

        # Prepare data for bulk operations
        voting_records_to_create = []
        voting_records_to_update = []

        # Get all speakers at once to avoid repeated database queries
        all_speakers = {
            speaker.naas_nm: speaker
            for speaker in Speaker.objects.all()
        }

        # Get existing voting records for this bill
        existing_records = {
            (record.speaker.naas_nm, record.bill_id): record
            for record in VotingRecord.objects.filter(
                bill=bill).select_related('speaker')
        }

        processed_count = 0
        skipped_count = 0

        for vote_item in voting_data:
            try:
                member_name = vote_item.get('HG_NM', '').strip()
                vote_result = vote_item.get('RESULT_VOTE_MOD', '').strip()
                vote_date_str = vote_item.get('VOTE_DATE', '')

                if not member_name or not vote_result:
                    skipped_count += 1
                    continue

                # Parse vote date
                vote_date = None
                if vote_date_str:
                    try:
                        vote_date = datetime.strptime(vote_date_str,
                                                      '%Y%m%d %H%M%S')
                    except ValueError:
                        logger.warning(
                            f"Could not parse vote date: {vote_date_str}")
                        vote_date = datetime.now()
                else:
                    vote_date = datetime.now()

                # Find the speaker by name from our cached dict
                speaker = None
                if member_name in all_speakers:
                    speaker = all_speakers[member_name]
                else:
                    # Try partial match
                    for speaker_name, speaker_obj in all_speakers.items():
                        if member_name in speaker_name or speaker_name in member_name:
                            speaker = speaker_obj
                            break

                if not speaker:
                    logger.warning(
                        f"Speaker not found for voting record: {member_name}")
                    skipped_count += 1
                    continue

                # Check if record already exists
                record_key = (member_name, bill_id)
                if record_key in existing_records:
                    # Update existing record
                    existing_record = existing_records[record_key]
                    existing_record.vote_result = vote_result
                    existing_record.vote_date = vote_date
                    existing_record.session = bill.session
                    voting_records_to_update.append(existing_record)
                else:
                    # Create new record
                    voting_record = VotingRecord(bill=bill,
                                                 speaker=speaker,
                                                 vote_result=vote_result,
                                                 vote_date=vote_date,
                                                 session=bill.session)
                    voting_records_to_create.append(voting_record)

                processed_count += 1

            except Exception as e_vote:
                logger.error(
                    f"❌ Error processing vote item for {bill_id}: {e_vote}. Item: {vote_item}"
                )
                skipped_count += 1
                continue

        # Perform bulk operations
        created_count = 0
        updated_count = 0

        if voting_records_to_create:
            try:
                VotingRecord.objects.bulk_create(voting_records_to_create,
                                                 ignore_conflicts=True)
                created_count = len(voting_records_to_create)
                logger.info(
                    f"✨ Bulk created {created_count} voting records for {bill.bill_nm[:30]}..."
                )
            except Exception as e_bulk_create:
                logger.error(f"❌ Error in bulk create: {e_bulk_create}")

        if voting_records_to_update:
            try:
                VotingRecord.objects.bulk_update(
                    voting_records_to_update,
                    ['vote_result', 'vote_date', 'session'],
                    batch_size=100)
                updated_count = len(voting_records_to_update)
                logger.info(
                    f"🔄 Bulk updated {updated_count} voting records for {bill.bill_nm[:30]}..."
                )
            except Exception as e_bulk_update:
                logger.error(f"❌ Error in bulk update: {e_bulk_update}")

        logger.info(
            f"🎉 Voting data processed for bill {bill_id}: {created_count} created, {updated_count} updated, {skipped_count} skipped, {processed_count} total processed."
        )

    except RequestException as re_exc:
        logger.error(
            f"Request error fetching voting data for {bill_id}: {re_exc}")
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for voting data {bill_id}.")
    except json.JSONDecodeError as json_e:
        logger.error(f"JSON decode error for voting data {bill_id}: {json_e}")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching voting data for {bill_id}: {e}")
        logger.exception(f"Full traceback for voting data {bill_id}:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected error for voting data {bill_id}."
            )


@with_db_retry
def create_placeholder_bill(session_obj, title, bill_no=None):
    """Creates a placeholder Bill for agenda items found only in the PDF."""
    unique_id_str = f"PDF_{session_obj.conf_id}_{hash(title)}"

    bill, created = Bill.objects.get_or_create(
        bill_id=unique_id_str,
        defaults={
            'session': session_obj,
            'bill_nm': title,
            'bill_no': bill_no,  # Will be None if not provided
            'proposer': None,  # Proposer is unknown from PDF agenda
        })
    if created:
        pass
        # Only log the rightmost party in the chain


def process_session_pdf_text(
        full_text,
        session_id,
        session_obj,
        bills_context_str,  # Deprecated
        bill_names_list_from_api,  # Now used as the "known_bill_names"
        debug=False):
    if not full_text:
        logger.warning(f"No text provided for session {session_id}")
        return

    logger.info(
        f"🔄 Processing PDF text for session {session_id} ({len(full_text)} chars)"
    )

    cleaned_text = clean_pdf_text(full_text)
    if not cleaned_text:
        logger.warning(
            f"No text remaining after cleaning for session {session_id}")
        return

    # Call the new all-in-one function. It handles discovery, placeholder creation, and segmentation.
    statements_data = extract_statements_with_llm_discovery(
        cleaned_text, session_id, bill_names_list_from_api, session_obj, debug)

    if not statements_data:
        logger.warning(
            f"No statements were extracted by the LLM discovery process for session {session_id}"
        )
        return

    logger.info(
        f"✅ Extracted {len(statements_data)} statements in total for session {session_id}"
    )
    process_extracted_statements_data(statements_data, session_obj, full_text,
                                      debug)


def process_pdf_text_for_statements(full_text,
                                    session_id,
                                    session_obj,
                                    bills_context_str,
                                    bill_names_list_from_api,
                                    debug=False):
    """Alias for process_session_pdf_text for future compatibility."""
    return process_session_pdf_text(full_text, session_id, session_obj,
                                    bills_context_str,
                                    bill_names_list_from_api, debug)


def clean_pdf_text(text: str) -> str:
    if not text:
        return ""

    original_len = len(text)

    # Find meeting start marker
    start_marker_match = re.search(r'\(\d{1,2}시\s*\d{1,2}분\s+개의\)', text)
    if not start_marker_match:
        logger.warning(
            "⚠️ No meeting start marker '(xx시xx분 개의)' found. Using fallback cleaning."
        )
        start_pos = 0
    else:
        start_pos = start_marker_match.end()  # Start AFTER the opening marker

    # Find meeting end markers
    end_marker_patterns = [
        r'\(\d{1,2}시\s*\d{1,2}분\s+산회\)',
        r'\(\d{1,2}시\s*\d{1,2}분\s+폐회\)',
    ]

    end_pos = len(text)
    for pattern in end_marker_patterns:
        end_marker_match = re.search(pattern, text[start_pos:])
        if end_marker_match:
            end_pos = start_pos + end_marker_match.start(
            )  # End BEFORE the closing marker
            break

    discussion_block = text[start_pos:end_pos]
    logger.info(
        f"📖 Isolated discussion block of {len(discussion_block)} chars (from original {original_len})."
    )

    # Enhanced cleaning patterns
    patterns_to_remove = [
        r'^제\d+회-제\d+차\s*\(.+?\)\s*\d*\s*$',  # Session headers
        r'^국\s*회\s*본\s*회\s*의\s*회\s*의\s*록\s*$',  # Meeting record headers
        r'^제\d+\s*$',  # Page numbers
        r'^\d{4}\s*$',  # Year numbers
        r'^\s*-\s*\d+\s*-\s*$',  # Page separators
        r'\(보고사항은\s*끝에\s*실음\)',  # Report notes
        r'^의사일정\s+제\d+항',  # Agenda items at start
        r'^국회사무처\s*$',  # Administrative notes
        r'^회의록\s*$',  # Record labels
    ]

    cleaned_lines = []
    lines = discussion_block.split('\n')

    # Skip initial header/metadata section until we find first speaker
    found_first_speaker = False

    for line in lines:
        stripped_line = line.strip()

        # Skip empty lines
        if not stripped_line:
            continue

        # Remove patterns
        skip_line = False
        for pattern in patterns_to_remove:
            if re.match(pattern, stripped_line, re.IGNORECASE):
                skip_line = True
                break

        if skip_line:
            continue

        # Look for first speaker marker (◯) to start actual content
        if not found_first_speaker:
            if stripped_line.startswith('◯'):
                found_first_speaker = True
            else:
                continue  # Skip everything before first speaker

        cleaned_lines.append(stripped_line)

    final_text = "\n".join(cleaned_lines)
    final_text = re.sub(r'\n{2,}', '\n',
                        final_text)  # Collapse multiple newlines

    logger.info(
        f"🧹 Text cleaning complete. Final length: {len(final_text)} chars. Found first speaker: {found_first_speaker}"
    )

    # Additional validation - ensure we have actual content
    if not found_first_speaker or len(final_text) < 100:
        logger.warning(
            "⚠️ Cleaned text appears to have no valid speaker content. Using less aggressive cleaning."
        )
        # Fallback: just remove obvious headers but keep more content
        fallback_lines = []
        for line in discussion_block.split('\n'):
            stripped = line.strip()
            if (stripped and not re.match(r'^제\d+회-제\d+차', stripped)
                    and not re.match(r'^국\s*회\s*본\s*회\s*의', stripped)
                    and not re.match(r'^\d{1,4}\s*$', stripped)):
                fallback_lines.append(stripped)
        final_text = "\n".join(fallback_lines)
        final_text = re.sub(r'\n{2,}', '\n', final_text)
        logger.info(
            f"🔄 Using fallback cleaning. Length: {len(final_text)} chars")

    return final_text


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_additional_data_nepjpxkkabqiqpbvk(self=None,
                                            force=False,
                                            debug=False):
    """Fetch additional data using nepjpxkkabqiqpbvk API endpoint."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Fetching additional data using nepjpxkkabqiqpbvk API"
            )

        url = "https://open.assembly.go.kr/portal/openapi/nepjpxkkabqiqpbvk"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "pIndex": 1,
            "pSize": 100
        }

        logger.info(f"🔍 Fetching additional data from nepjpxkkabqiqpbvk API")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        logger.info(
            f"📊 nepjpxkkabqiqpbvk API response structure: {list(data.keys()) if data else 'Empty response'}"
        )

        if debug:
            logger.info(
                f"🐛 DEBUG: Full nepjpxkkabqiqpbvk response: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        # Extract data based on API structure
        additional_data = None
        if 'nepjpxkkabqiqpbvk' in data and len(data['nepjpxkkabqiqpbvk']) > 1:
            additional_data = data['nepjpxkkabqiqpbvk'][1].get('row', [])
        elif 'nepjpxkkabqiqpbvk' in data and len(
                data['nepjpxkkabqiqpbvk']) > 0:
            additional_data = data['nepjpxkkabqiqpbvk'][0].get('row', [])
        elif 'row' in data:
            additional_data = data['row']

        if not additional_data:
            logger.info(
                f"ℹ️  No additional data found from nepjpxkkabqiqpbvk API")
            return

        logger.info(
            f"✅ Found {len(additional_data)} records from nepjpxkkabqiqpbvk API"
        )

        # Process the additional data (customize based on what the API returns)
        processed_count = 0
        for item in additional_data:
            try:
                if debug:
                    logger.info(f"🐛 DEBUG: Processing item: {item}")
                else:
                    # Process the item based on its structure
                    # This will depend on what nepjpxkkabqiqpbvk actually returns
                    processed_count += 1

            except Exception as e:
                logger.error(f"❌ Error processing nepjpxkkabqiqpbvk item: {e}")
                continue

        logger.info(
            f"🎉 Processed {processed_count} items from nepjpxkkabqiqpbvk API")

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        f"Max retries exceeded for nepjpxkkabqiqpbvk fetch")
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        else:
            logger.error(f"❌ Error fetching from nepjpxkkabqiqpbvk API: {e}")
            raise
