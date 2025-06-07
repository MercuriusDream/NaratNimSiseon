import requests
import pdfplumber
from celery import shared_task
from django.conf import settings
from .models import Session, Bill, Speaker, Statement
from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import RequestException
import logging
from celery.schedules import crontab
from datetime import datetime, timedelta, time as dt_time
import json
import os
import time
from pathlib import Path

print("🐛 IMMEDIATE DEBUG: Configuring logger")
logger = logging.getLogger(__name__)
print(f"🐛 IMMEDIATE DEBUG: Logger configured: {logger}")
print(f"🐛 IMMEDIATE DEBUG: Logger level: {logger.level}")
print(f"🐛 IMMEDIATE DEBUG: Logger handlers: {logger.handlers}")

# Configure logger to actually show output
import sys

logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
print(
    f"🐛 IMMEDIATE DEBUG: Logger reconfigured with handlers: {logger.handlers}")

# Configure Gemini API with error handling
try:
    import google.generativeai as genai
    if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemma-3-27b-it')
    else:
        logger.warning("GEMINI_API_KEY not found in settings")
        genai = None
        model = None
except ImportError:
    logger.warning("google.generativeai not available")
    genai = None
    model = None
except Exception as e:
    logger.warning(f"Error configuring Gemini API: {e}")
    genai = None
    model = None


# Check if Celery/Redis is available
def is_celery_available():
    """Check if Celery/Redis is available for async tasks"""
    from kombu.exceptions import OperationalError
    from celery import current_app
    try:
        current_app.control.inspect().active()
        return True
    except (ImportError, OperationalError, OSError, ConnectionError):
        return False


# Decorator to handle both sync and async execution
def celery_or_sync(func):
    """Decorator that runs function sync if Celery is not available"""

    def wrapper(*args, **kwargs):
        if is_celery_available():
            logger.info(
                f"🔄 Running {func.__name__} asynchronously with Celery")
            return func.delay(*args, **kwargs)
        else:
            logger.info(
                f"🔄 Running {func.__name__} synchronously (Celery not available)"
            )
            # Remove 'self' parameter if it's a bound task
            if hasattr(func, '__wrapped__'):
                return func.__wrapped__(*args, **kwargs)
            else:
                return func(*args, **kwargs)

    return wrapper


from celery import shared_task
import logging
from .utils import DataCollector
from .llm_analyzer import LLMPolicyAnalyzer

logger = logging.getLogger(__name__)


def format_conf_id(conf_id):
    """Format CONF_ID to be zero-filled to 6 digits."""
    return str(conf_id).zfill(6)


def fetch_speaker_details(speaker_name):
    """Fetch speaker details from ALLNAMEMBER API"""
    try:
        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "NAAS_NM": speaker_name,
            "Type": "json"
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        logger.info(
            f"🐛 DEBUG: ALLNAMEMBER API response for {speaker_name}: {json.dumps(data, indent=2, ensure_ascii=False)}"
        )

        # Extract member data
        member_data = None
        if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
            rows = data['ALLNAMEMBER'][1].get('row', [])
            if rows and len(rows) > 0:
                member_data = rows[0]  # Get first match

        if member_data:
            # Create or update speaker with detailed information
            speaker, created = Speaker.objects.get_or_create(
                naas_cd=member_data.get('NAAS_CD', f"TEMP_{speaker_name}"),
                defaults={
                    'naas_nm': member_data.get('NAAS_NM', speaker_name),
                    'naas_ch_nm': member_data.get('NAAS_CH_NM', ''),
                    'plpt_nm': member_data.get('PLPT_NM', '정당정보없음'),
                    'elecd_nm': member_data.get('ELECD_NM', ''),
                    'elecd_div_nm': member_data.get('ELECD_DIV_NM', ''),
                    'cmit_nm': member_data.get('CMIT_NM', ''),
                    'blng_cmit_nm': member_data.get('BLNG_CMIT_NM', ''),
                    'rlct_div_nm': member_data.get('RLCT_DIV_NM', ''),
                    'gtelt_eraco': member_data.get('GTELT_ERACO', ''),
                    'ntr_div': member_data.get('NTR_DIV', ''),
                    'naas_pic': member_data.get('NAAS_PIC', '')
                })

            if not created:
                # Update existing speaker with new information
                speaker.naas_nm = member_data.get('NAAS_NM', speaker.naas_nm)
                speaker.naas_ch_nm = member_data.get('NAAS_CH_NM',
                                                     speaker.naas_ch_nm)
                speaker.plpt_nm = member_data.get('PLPT_NM', speaker.plpt_nm)
                speaker.elecd_nm = member_data.get('ELECD_NM',
                                                   speaker.elecd_nm)
                speaker.elecd_div_nm = member_data.get('ELECD_DIV_NM',
                                                       speaker.elecd_div_nm)
                speaker.cmit_nm = member_data.get('CMIT_NM', speaker.cmit_nm)
                speaker.blng_cmit_nm = member_data.get('BLNG_CMIT_NM',
                                                       speaker.blng_cmit_nm)
                speaker.rlct_div_nm = member_data.get('RLCT_DIV_NM',
                                                      speaker.rlct_div_nm)
                speaker.gtelt_eraco = member_data.get('GTELT_ERACO',
                                                      speaker.gtelt_eraco)
                speaker.ntr_div = member_data.get('NTR_DIV', speaker.ntr_div)
                speaker.naas_pic = member_data.get('NAAS_PIC',
                                                   speaker.naas_pic)
                speaker.save()

            logger.info(
                f"✅ Fetched/updated speaker details for: {speaker_name}")
            return speaker
        else:
            logger.warning(f"⚠️ No member data found for: {speaker_name}")
            return None

    except Exception as e:
        logger.error(
            f"❌ Error fetching speaker details for {speaker_name}: {e}")
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_continuous_sessions(self=None,
                              force=False,
                              debug=False,
                              start_date=None):
    """Fetch sessions starting from a specific date or continue from last session."""
    try:
        logger.info(
            f"🔍 Starting continuous session fetch (force={force}, debug={debug}, start_date={start_date})"
        )

        # Check if we have the required settings
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("❌ ASSEMBLY_API_KEY not configured")
            raise ValueError("ASSEMBLY_API_KEY not configured")

        url = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"

        # Determine starting point
        if start_date:
            from datetime import datetime
            start_datetime = datetime.fromisoformat(start_date)
            logger.info(
                f"📅 Continuing from date: {start_datetime.strftime('%Y-%m')}")
        else:
            start_datetime = datetime.now()
            logger.info(
                f"📅 Starting from current date: {start_datetime.strftime('%Y-%m')}"
            )

        # Fetch sessions month by month going backwards from start date
        current_date = start_datetime
        sessions_found = False

        for months_back in range(0, 36):  # Go back up to 36 months
            # Calculate target month
            year = current_date.year
            month = current_date.month - months_back

            # Handle year rollover
            while month <= 0:
                month += 12
                year -= 1

            conf_date = f"{year:04d}-{month:02d}"

            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "DAE_NUM": "22",  # 22nd Assembly
                "CONF_DATE": conf_date
            }

            logger.info(f"📅 Fetching sessions for: {conf_date}")

            if debug:
                logger.info(f"🐛 DEBUG: API URL: {url}")
                logger.info(f"🐛 DEBUG: API Params for {conf_date}: {params}")

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if debug:
                    logger.info(
                        f"🐛 DEBUG: API Response status for {conf_date}: {response.status_code}"
                    )

                sessions_data = extract_sessions_from_response(data,
                                                               debug=debug)

                if sessions_data:
                    sessions_found = True
                    logger.info(
                        f"✅ Found {len(sessions_data)} sessions for {conf_date}"
                    )

                    # Process sessions for this month
                    process_sessions_data(sessions_data,
                                          force=force,
                                          debug=debug)

                    # Small delay between requests to be respectful
                    if not debug:
                        time.sleep(1)
                else:
                    logger.info(f"❌ No sessions found for {conf_date}")

                    # If we haven't found any sessions in the last 6 months, stop
                    if months_back > 6 and not sessions_found:
                        logger.info(
                            "🛑 No sessions found in recent months, stopping search"
                        )
                        break

            except Exception as e:
                logger.warning(f"⚠️ Error fetching {conf_date}: {e}")
                if debug:
                    logger.info(
                        f"🐛 DEBUG: Full error for {conf_date}: {type(e).__name__}: {e}"
                    )
                continue

        # After session collection, fetch additional data
        if not debug and sessions_found:
            logger.info("🔄 Starting additional data collection...")
            if is_celery_available():
                fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force,
                                                              debug=debug)
            else:
                fetch_additional_data_nepjpxkkabqiqpbvk(force=force,
                                                        debug=debug)

        if sessions_found:
            logger.info("🎉 Continuous session fetch completed")
        else:
            logger.info("ℹ️ No new sessions found during continuous fetch")

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        "Max retries exceeded for fetch_continuous_sessions")
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        logger.error(f"❌ Critical error in fetch_continuous_sessions: {e}")
        logger.error(f"📊 Session count in DB: {Session.objects.count()}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_latest_sessions(self=None, force=False, debug=False):
    """Fetch latest assembly sessions from the API."""
    # Add immediate debug output
    print(
        f"🐛 IMMEDIATE DEBUG: Function called with force={force}, debug={debug}"
    )

    try:
        print(f"🐛 IMMEDIATE DEBUG: About to call logger.info")
        logger.info(f"🔍 Starting session fetch (force={force}, debug={debug})")
        print(f"🐛 IMMEDIATE DEBUG: Logger.info called successfully")

        # Check if we have the required settings
        print(f"🐛 IMMEDIATE DEBUG: Checking settings")
        if not hasattr(settings, 'ASSEMBLY_API_KEY'):
            print(f"🐛 IMMEDIATE DEBUG: ASSEMBLY_API_KEY attribute not found")
            logger.error("❌ ASSEMBLY_API_KEY not found in settings")
            raise ValueError("ASSEMBLY_API_KEY not configured")

        if not settings.ASSEMBLY_API_KEY:
            print(f"🐛 IMMEDIATE DEBUG: ASSEMBLY_API_KEY is empty")
            logger.error("❌ ASSEMBLY_API_KEY is empty")
            raise ValueError("ASSEMBLY_API_KEY not configured")

        print(f"🐛 IMMEDIATE DEBUG: Settings check passed")
        print(
            f"🐛 IMMEDIATE DEBUG: API Key exists: {bool(settings.ASSEMBLY_API_KEY)}"
        )
        print(
            f"🐛 IMMEDIATE DEBUG: API Key first 10 chars: {settings.ASSEMBLY_API_KEY[:10]}..."
        )

        if debug:
            print(f"🐛 DEBUG: Function started successfully")
            print(f"🐛 DEBUG: Settings check passed")
            logger.info(f"🐛 DEBUG: Function started successfully")
            logger.info(f"🐛 DEBUG: Settings check passed")

    except Exception as e:
        print(f"🐛 IMMEDIATE DEBUG: Exception caught: {e}")
        print(f"🐛 IMMEDIATE DEBUG: Exception type: {type(e).__name__}")
        logger.error(f"❌ Error at start of fetch_latest_sessions: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        import traceback
        traceback_str = traceback.format_exc()
        print(f"🐛 IMMEDIATE DEBUG: Traceback: {traceback_str}")
        logger.error(f"❌ Full traceback: {traceback_str}")
        raise

    try:
        print(f"🐛 IMMEDIATE DEBUG: About to start API calls")
        url = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"
        print(f"🐛 IMMEDIATE DEBUG: URL set to: {url}")

        # If not force, only fetch recent sessions
        if not force:
            print(
                f"🐛 IMMEDIATE DEBUG: Not force mode, fetching current month only"
            )
            # Fetch current month only
            current_date = datetime.now()
            conf_date = (current_date - timedelta(days=30)).strftime('%Y-%m')
            print(
                f"🐛 IMMEDIATE DEBUG: Current date calculated as: {conf_date}")
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "DAE_NUM": "22",  # 22nd Assembly
                "CONF_DATE": conf_date
            }
            print(f"🐛 IMMEDIATE DEBUG: Params created: {params}")
            logger.info(
                f"📅 Fetching sessions for: {(current_date-timedelta(days=30)).strftime('%Y-%m')}"
            )

            if debug:
                print(f"🐛 DEBUG: API URL: {url}")
                print(f"🐛 DEBUG: API Params: {params}")
                logger.info(f"🐛 DEBUG: API URL: {url}")
                logger.info(f"🐛 DEBUG: API Params: {params}")

            print(f"🐛 IMMEDIATE DEBUG: About to make API request")
            response = requests.get(url, params=params, timeout=30)
            print(
                f"🐛 IMMEDIATE DEBUG: API request completed, status: {response.status_code}"
            )
            response.raise_for_status()
            print(f"🐛 IMMEDIATE DEBUG: Response status check passed")
            data = response.json()
            print(
                f"🐛 IMMEDIATE DEBUG: JSON parsing completed, data type: {type(data)}"
            )

            if debug:
                print(f"🐛 DEBUG: API Response status: {response.status_code}")
                print(
                    f"🐛 DEBUG: Full API response: {json.dumps(data, indent=2, ensure_ascii=False)}"
                )
                logger.info(
                    f"🐛 DEBUG: API Response status: {response.status_code}")
                logger.info(
                    f"🐛 DEBUG: Full API response: {json.dumps(data, indent=2, ensure_ascii=False)}"
                )

            print(
                f"🐛 IMMEDIATE DEBUG: About to extract sessions from response")
            sessions_data = extract_sessions_from_response(data, debug=debug)
            print(
                f"🐛 IMMEDIATE DEBUG: Sessions extraction completed, found {len(sessions_data) if sessions_data else 0} sessions"
            )

            if sessions_data:
                print(
                    f"🐛 IMMEDIATE DEBUG: About to process {len(sessions_data)} sessions"
                )
                process_sessions_data(sessions_data, force=force, debug=debug)
                print(f"🐛 IMMEDIATE DEBUG: Sessions processing completed")
            elif debug:
                print("🐛 DEBUG: No sessions data found to process")
                print(
                    f"🐛 DEBUG: Raw API response keys: {list(data.keys()) if data else 'No data'}"
                )
                logger.info("🐛 DEBUG: No sessions data found to process")
                logger.info(
                    f"🐛 DEBUG: Raw API response keys: {list(data.keys()) if data else 'No data'}"
                )
                if data:
                    for key, value in data.items():
                        print(
                            f"🐛 DEBUG: {key}: {type(value)} - {str(value)[:200]}..."
                        )
                        logger.info(
                            f"🐛 DEBUG: {key}: {type(value)} - {str(value)[:200]}..."
                        )
            else:
                print("❌ No sessions data found in API response")
                logger.info("❌ No sessions data found in API response")
        else:
            # Force mode: fetch month by month going backwards
            print(f"🐛 IMMEDIATE DEBUG: Force mode enabled")
            logger.info("🔄 Force mode: Fetching sessions month by month")
            current_date = datetime.now() - timedelta(days=30)
            print(
                f"🐛 IMMEDIATE DEBUG: Starting from current date: {current_date}"
            )

            for months_back in range(0, 24):  # Go back up to 24 months
                # Use proper month calculation instead of days
                year = current_date.year
                month = current_date.month - months_back

                # Handle year rollover
                while month <= 0:
                    month += 12
                    year -= 1

                conf_date = f"{year:04d}-{month:02d}"
                print(
                    f"🐛 IMMEDIATE DEBUG: Calculated conf_date for months_back={months_back}: {conf_date}"
                )

                params = {
                    "KEY": settings.ASSEMBLY_API_KEY,
                    "Type": "json",
                    "DAE_NUM": "22",  # 22nd Assembly
                    "CONF_DATE": conf_date
                }

                logger.info(f"📅 Fetching sessions for: {conf_date}")

                if debug:
                    logger.info(f"🐛 DEBUG: API URL: {url}")
                    logger.info(
                        f"🐛 DEBUG: API Params for {conf_date}: {params}")

                try:
                    response = requests.get(url, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()

                    if debug:
                        logger.info(
                            f"🐛 DEBUG: API Response status for {conf_date}: {response.status_code}"
                        )
                        logger.info(
                            f"🐛 DEBUG: Full API response for {conf_date}: {json.dumps(data, indent=2, ensure_ascii=False)}"
                        )

                    sessions_data = extract_sessions_from_response(data,
                                                                   debug=debug)
                    if not sessions_data:
                        logger.info(
                            f"❌ No sessions found for {conf_date}, stopping..."
                        )
                        if debug:
                            logger.info(
                                f"🐛 DEBUG: Breaking loop at {conf_date}")
                        break

                    process_sessions_data(sessions_data,
                                          force=force,
                                          debug=debug)

                    # Small delay between requests to be respectful
                    if not debug:  # Skip delay in debug mode for faster testing
                        time.sleep(1)

                except Exception as e:
                    logger.warning(f"⚠️ Error fetching {conf_date}: {e}")
                    if debug:
                        logger.info(
                            f"🐛 DEBUG: Full error for {conf_date}: {type(e).__name__}: {e}"
                        )
                    continue

        # After session collection, fetch additional data
        if not debug:
            logger.info("🔄 Starting additional data collection...")
            if is_celery_available():
                fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force,
                                                              debug=debug)
            else:
                fetch_additional_data_nepjpxkkabqiqpbvk(force=force,
                                                        debug=debug)

        logger.info("🎉 Session fetch completed")

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        "Max retries exceeded for fetch_latest_sessions")
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        logger.error(f"❌ Critical error in fetch_latest_sessions: {e}")
        logger.error(f"📊 Session count in DB: {Session.objects.count()}")
        raise


def extract_sessions_from_response(data, debug=False):
    """Extract sessions data from API response"""
    print(
        f"🐛 IMMEDIATE DEBUG: extract_sessions_from_response called with debug={debug}"
    )
    print(f"🐛 IMMEDIATE DEBUG: Data type: {type(data)}")
    print(
        f"🐛 IMMEDIATE DEBUG: Data keys: {list(data.keys()) if data else 'Empty response'}"
    )

    if debug:
        print(
            f"🐛 DEBUG: Full API response structure: {list(data.keys()) if data else 'Empty response'}"
        )
        logger.info(
            f"🐛 DEBUG: Full API response structure: {list(data.keys()) if data else 'Empty response'}"
        )
        if data and 'nzbyfwhwaoanttzje' in data:
            print(
                f"🐛 DEBUG: nzbyfwhwaoanttzje length: {len(data['nzbyfwhwaoanttzje'])}"
            )
            logger.info(
                f"🐛 DEBUG: nzbyfwhwaoanttzje length: {len(data['nzbyfwhwaoanttzje'])}"
            )
            if len(data['nzbyfwhwaoanttzje']) > 0:
                print(
                    f"🐛 DEBUG: First element keys: {list(data['nzbyfwhwaoanttzje'][0].keys()) if isinstance(data['nzbyfwhwaoanttzje'][0], dict) else 'Not a dict'}"
                )
                print(
                    f"🐛 DEBUG: First element: {data['nzbyfwhwaoanttzje'][0]}")
                logger.info(
                    f"🐛 DEBUG: First element keys: {list(data['nzbyfwhwaoanttzje'][0].keys()) if isinstance(data['nzbyfwhwaoanttzje'][0], dict) else 'Not a dict'}"
                )
            if len(data['nzbyfwhwaoanttzje']) > 1:
                print(
                    f"🐛 DEBUG: Second element keys: {list(data['nzbyfwhwaoanttzje'][1].keys()) if isinstance(data['nzbyfwhwaoanttzje'][1], dict) else 'Not a dict'}"
                )
                print(
                    f"🐛 DEBUG: Second element: {data['nzbyfwhwaoanttzje'][1]}")
                logger.info(
                    f"🐛 DEBUG: Second element keys: {list(data['nzbyfwhwaoanttzje'][1].keys()) if isinstance(data['nzbyfwhwaoanttzje'][1], dict) else 'Not a dict'}"
                )

    sessions_data = None
    print(f"🐛 IMMEDIATE DEBUG: Starting sessions data extraction")

    if 'nzbyfwhwaoanttzje' in data and len(data['nzbyfwhwaoanttzje']) > 1:
        print(f"🐛 IMMEDIATE DEBUG: Using second element for sessions data")
        sessions_data = data['nzbyfwhwaoanttzje'][1].get('row', [])
        if debug:
            print(f"🐛 DEBUG: Using second element for sessions data")
            logger.info(f"🐛 DEBUG: Using second element for sessions data")
    elif 'nzbyfwhwaoanttzje' in data and len(data['nzbyfwhwaoanttzje']) > 0:
        print(
            f"🐛 IMMEDIATE DEBUG: Using first element as fallback for sessions data"
        )
        # Try first element as fallback
        sessions_data = data['nzbyfwhwaoanttzje'][0].get('row', [])
        if debug:
            print(
                f"🐛 DEBUG: Using first element as fallback for sessions data")
            logger.info(
                f"🐛 DEBUG: Using first element as fallback for sessions data")
    elif 'row' in data:
        print(f"🐛 IMMEDIATE DEBUG: Using direct 'row' key for sessions data")
        # Fallback for old API structure
        sessions_data = data['row']
        if debug:
            print(f"🐛 DEBUG: Using direct 'row' key for sessions data")
            logger.info(f"🐛 DEBUG: Using direct 'row' key for sessions data")
    else:
        print(
            f"🐛 IMMEDIATE DEBUG: No sessions data found in any expected location"
        )

    print(
        f"🐛 IMMEDIATE DEBUG: Extracted {len(sessions_data) if sessions_data else 0} sessions from response"
    )

    if debug:
        print(
            f"🐛 DEBUG: Extracted {len(sessions_data) if sessions_data else 0} sessions from response"
        )
        logger.info(
            f"🐛 DEBUG: Extracted {len(sessions_data) if sessions_data else 0} sessions from response"
        )
        if sessions_data and len(sessions_data) > 0:
            print(
                f"🐛 DEBUG: Sample session keys: {list(sessions_data[0].keys())}"
            )
            print(f"🐛 DEBUG: First session sample data: {sessions_data[0]}")
            logger.info(
                f"🐛 DEBUG: Sample session keys: {list(sessions_data[0].keys())}"
            )
            logger.info(
                f"🐛 DEBUG: First session sample data: {sessions_data[0]}")
        else:
            print(f"🐛 DEBUG: No session data found in response")
            logger.info(f"🐛 DEBUG: No session data found in response")

    print(
        f"✅ Found {len(sessions_data) if sessions_data else 0} sessions in API response"
    )
    logger.info(
        f"✅ Found {len(sessions_data) if sessions_data else 0} sessions in API response"
    )
    return sessions_data


def process_sessions_data(sessions_data, force=False, debug=False):
    """Process the sessions data and create/update session objects"""
    print(
        f"🐛 IMMEDIATE DEBUG: process_sessions_data called with {len(sessions_data) if sessions_data else 0} sessions, debug={debug}"
    )

    if not sessions_data:
        print("❌ No sessions data to process")
        logger.warning("❌ No sessions data to process")
        return

    # Always show the first few sessions to understand the data structure
    '''
    print("🔍 RAW API SESSION DATA STRUCTURE:")
    print("=" * 80)
    for i, row in enumerate(sessions_data[:5],
                            1):  # Show first 5 sessions always
        print(f"📋 SESSION {i} RAW DATA:")
        print(f"   Type: {type(row)}")
        print(
            f"   Keys: {list(row.keys()) if isinstance(row, dict) else 'Not a dict'}"
        )

        # Show all key-value pairs
        if isinstance(row, dict):
            for key, value in row.items():
                print(f"   {key}: {value}")
        else:
            print(f"   Full value: {row}")
        print("   " + "-" * 60)
    print("=" * 80)
    '''

    # Group sessions by CONFER_NUM since multiple agenda items can belong to the same session
    sessions_by_id = {}
    for row in sessions_data:
        session_id = row.get('CONFER_NUM')
        if session_id:
            if session_id not in sessions_by_id:
                sessions_by_id[session_id] = []
            sessions_by_id[session_id].append(row)

    print(
        f"🔍 GROUPED SESSIONS: Found {len(sessions_by_id)} unique sessions from {len(sessions_data)} agenda items"
    )
    logger.info(
        f"🔍 GROUPED SESSIONS: Found {len(sessions_by_id)} unique sessions from {len(sessions_data)} agenda items"
    )

    if debug:
        print(
            f"🐛 DEBUG MODE: Processing {len(sessions_by_id)} unique sessions (preview only - no database writes)"
        )
        logger.info(
            f"🐛 DEBUG MODE: Processing {len(sessions_by_id)} unique sessions (preview only - no database writes)"
        )

        for i, (session_id, agenda_items) in enumerate(sessions_by_id.items(),
                                                       1):
            first_item = agenda_items[
                0]  # Use first agenda item for main session info
            title = first_item.get('TITLE', 'Unknown')
            date = first_item.get('CONF_DATE', 'Unknown')
            pdf_url = first_item.get('PDF_LINK_URL', 'No PDF')

            print(f"🐛 DEBUG Session {i}: ID={session_id}")
            print(f"   Title: {title}")
            print(f"   Date: {date}")
            print(f"   PDF: {pdf_url}")
            print(f"   Agenda items: {len(agenda_items)}")
            for j, item in enumerate(agenda_items, 1):
                print(
                    f"     {j}. {item.get('SUB_NAME', 'No agenda item name')}")
            print("   ---")

            logger.info(f"🐛 DEBUG Session {i}: ID={session_id}")
            logger.info(f"   Title: {title}")
            logger.info(f"   Date: {date}")
            logger.info(f"   PDF: {pdf_url}")
            logger.info(f"   Agenda items: {len(agenda_items)}")

        print("🐛 DEBUG MODE: Data preview completed - not storing to database")
        logger.info(
            "🐛 DEBUG MODE: Data preview completed - not storing to database")
        return

    created_count = 0
    updated_count = 0

    for i, (session_id, agenda_items) in enumerate(sessions_by_id.items(), 1):
        # Use the first agenda item for the main session information
        row = agenda_items[0]
        try:
            logger.info(
                f"🔄 Processing session {i}/{len(sessions_by_id)}: {row.get('TITLE', 'Unknown')} ({len(agenda_items)} agenda items)"
            )

            if not session_id:
                logger.warning(f"⚠️ No CONFER_NUM found for session {i}")
                continue

            # Parse date properly
            conf_date = None
            if row.get('CONF_DATE'):
                try:
                    conf_date = datetime.strptime(row.get('CONF_DATE'),
                                                  '%Y년 %m월 %d일').date()
                except ValueError:
                    try:
                        conf_date = datetime.strptime(row.get('CONF_DATE'),
                                                      '%Y-%m-%d').date()
                    except ValueError:
                        logger.warning(
                            f"Could not parse date: {json'):
            stage1_text = stage1_text[7:-3].strip()
        elif stage1_text.startswith('```'):
            stage1_text = stage1_text[3:-3].strip()

        import json as json_module
        stage1_data = json_module.loads(stage1_text)
        speakers_detected = stage1_data.get('speakers_detected', [])

        logger.info(f"✅ Speaker detection for {bill_name}: Found {len(speakers_detected)} potential speakers")

        # Stage 2: Extract and analyze substantial policy discussions
        analyzed_statements = []

        for i, speaker_info in enumerate(speakers_detected, 1):
            speaker_name = speaker_info.get('speaker_name', 'Unknown')
            is_substantial = speaker_info.get('is_substantial', False)
            is_real_person = speaker_info.get('is_real_person', False)
            speech_type = speaker_info.get('speech_type', 'unknown')
            bill_relevance = speaker_info.get('bill_relevance', 0.0)

            # Enhanced filtering for bill-specific content
            if not is_real_person or not is_substantial or speech_type != 'policy_discussion' or bill_relevance < 0.4:
                logger.info(f"⚠️ Skipping speaker {speaker_name} for {bill_name} - filters failed")
                continue

            # Extract speech content
            start_marker = speaker_info.get('start_marker', '')
            end_marker = speaker_info.get('end_marker', '')

            speech_content = extract_speech_between_markers(
                bill_text, start_marker, end_marker, speaker_name)

            if not speech_content or len(speech_content) < 10:
                continue

            # Stage 2: Analyze the extracted speech with bill context
            analysis_result = analyze_single_statement_with_bill_context(
                {
                    'speaker_name': speaker_name,
                    'text': speech_content
                }, session_id, bill_name, debug)

            analyzed_statements.append(analysis_result)

            # Brief pause between API calls
            if not debug:
                time.sleep(0.5)

        logger.info(f"✅ {bill_name} analysis completed: {len(analyzed_statements)} statements")
        return analyzed_statements

    except Exception as e:
        logger.error(f"❌ Error processing bill segment {bill_name}: {e}")
        return []


def analyze_single_statement_with_bill_context(statement_data, session_id, bill_name, debug=False):
    """Analyze a single statement with specific bill context."""
    if not model:
        logger.warning("❌ LLM model not available for statement analysis")
        return statement_data

    speaker_name = statement_data.get('speaker_name', '')
    text = statement_data.get('text', '')

    prompt = f"""
다음 국회 발언을 분석하여 감성 분석과 정책 분류를 수행해주세요.

발언자: {speaker_name}
관련 의안: {bill_name}
발언 내용: {text}

다음 JSON 형식으로 분석 결과를 제공해주세요:
{{
    "sentiment_score": -1부터 1까지의 감성 점수 (숫자),
    "sentiment_reason": "감성 분석 근거",
    "bill_relevance_score": 0부터 1까지의 의안 관련성 점수 (숫자),
    "policy_categories": [
        {{
            "main_category": "주요 정책 분야 (경제, 사회복지, 교육, 외교안보, 환경, 법무, 과학기술, 문화체육, 농림축산, 국정감사 중 하나)",
            "sub_category": "세부 분야",
            "confidence": 0부터 1까지의 확신도 (숫자)
        }}
    ],
    "policy_keywords": ["정책 관련 주요 키워드들"],
    "bill_specific_keywords": ["{bill_name}과 관련된 특정 키워드들"]
}}

분석 기준:
1. 감성 분석: -1(매우 부정적) ~ 1(매우 긍정적)
2. 의안 관련성: 0(무관) ~ 1(직접적 관련)
3. 정책 분류: 발언 내용과 의안을 종합적으로 고려
4. 키워드: 정책 일반 키워드와 의안별 특수 키워드 구분

응답은 반드시 유효한 JSON 형식이어야 합니다.
"""

    try:
        response = model.generate_content(prompt)

        if not response.text:
            logger.warning(f"❌ No LLM response for statement from {speaker_name}")
            return statement_data

        # Clean response
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        elif response_text.startswith('```'):
            response_text = response_text[3:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()

        # Parse JSON
        import json as json_module
        analysis_data = json_module.loads(response_text)

        # Merge analysis data with original statement
        statement_data.update({
            'sentiment_score': analysis_data.get('sentiment_score', 0.0),
            'sentiment_reason': analysis_data.get('sentiment_reason', 'LLM 분석 완료'),
            'bill_relevance_score': analysis_data.get('bill_relevance_score', 0.0),
            'policy_categories': analysis_data.get('policy_categories', []),
            'policy_keywords': analysis_data.get('policy_keywords', []),
            'bill_specific_keywords': analysis_data.get('bill_specific_keywords', [])
        })

        if debug:
            logger.info(f"🐛 DEBUG: Analyzed statement from {speaker_name} for {bill_name} - Sentiment: {statement_data.get('sentiment_score', 0)}, Bill relevance: {statement_data.get('bill_relevance_score', 0)}")

        return statement_data

    except Exception as e:
        logger.error(f"❌ Error analyzing statement from {speaker_name} for {bill_name}: {e}")
        return statement_data


def extract_statements_without_bill_separation(text, session_id, bills_context, debug=False):
    """Fallback to original extraction method when bill separation fails."""
    logger.info(f"🔄 Using standard extraction without bill separation for session: {session_id}")

    # Configure model for speaker detection
    speaker_detection_model = genai.GenerativeModel('gemini-2.0-flash-lite')

    speaker_detection_prompt = f"""
당신은 기록가입니다. 다음은 국회 회의록 텍스트입니다. 이 텍스트에서 실제 국회의원들의 발언 구간을 정확히 식별해주세요.

회의 관련 의안:
{bills_context}

회의록 텍스트:
{text}

다음 기준으로 발언을 식별해주세요:
1. ◯ 기호로 시작하는 발언만 추출
2. 발언자가 실제 사람 이름인지 판단 (한국 성씨로 시작하는 2-4글자 이름)
3. 법률명, 기관명, 직책명만 있는 경우는 제외
4. 절차적 발언과 정책 토론을 구분하여 분류
5. 발언 내용의 실질성 판단

JSON 형식으로 응답해주세요:
{{
    "speakers_detected": [
        {{
            "speaker_name": "정리된 발언자 실명",
            "original_speaker_text": "원본 발언자 텍스트",
            "start_marker": "발언 시작 부분 텍스트 (20자)",
            "end_marker": "발언 종료 부분 텍스트 (20자)",
            "is_substantial": true/false,
            "is_real_person": true/false,
            "speech_type": "policy_discussion/procedural/other",
            "filtering_reason": "판단 근거"
        }}
    ]
}}
"""

    try:
        stage1_response = speaker_detection_model.generate_content(speaker_detection_prompt)

        if not stage1_response.text:
            return []

        # Parse and process similar to the bill-separated version
        stage1_text = stage1_response.text.strip()
        if stage1_text.startswith('```json'):
            stage1_text = stage1_text[7:-3].strip()
        elif stage1_text.startswith('