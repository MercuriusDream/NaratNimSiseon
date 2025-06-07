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
                            f"Could not parse date: {row.get('CONF_DATE')}")
                        conf_date = None

            session, created = Session.objects.get_or_create(
                conf_id=session_id,
                defaults={
                    'era_co':
                    f'제{row.get("DAE_NUM", 22)}대',
                    'sess':
                    row.get('TITLE', '').split(' ')[2] if len(
                        row.get('TITLE', '').split(' ')) > 2 else '',
                    'dgr':
                    row.get('TITLE', '').split(' ')[3] if len(
                        row.get('TITLE', '').split(' ')) > 3 else '',
                    'conf_dt':
                    conf_date,
                    'conf_knd':
                    row.get('CLASS_NAME', '국회본회의'),
                    'cmit_nm':
                    row.get('CLASS_NAME', '국회본회의'),
                    'bg_ptm':
                    dt_time(9, 0),  # Default time since API doesn't provide it
                    'down_url':
                    row.get('PDF_LINK_URL', '')
                })

            if created:
                created_count += 1
                logger.info(f"✨ Created new session: {session_id}")
            else:
                logger.info(f"♻️  Session already exists: {session_id}")

            # If session exists and force is True, update the session
            if not created and force:
                session.era_co = f'제{row.get("DAE_NUM", 22)}대'
                session.sess = row.get('TITLE', '').split(' ')[2] if len(
                    row.get('TITLE', '').split(' ')) > 2 else ''
                session.dgr = row.get('TITLE', '').split(' ')[3] if len(
                    row.get('TITLE', '').split(' ')) > 3 else ''
                session.conf_dt = conf_date
                session.conf_knd = row.get('CLASS_NAME', '국회본회의')
                session.cmit_nm = row.get('CLASS_NAME', '국회본회의')
                session.down_url = row.get('PDF_LINK_URL', '')
                if not session.bg_ptm:  # Only update if not already set
                    session.bg_ptm = dt_time(9, 0)
                session.save()
                updated_count += 1
                logger.info(f"🔄 Updated existing session: {session_id}")

            # Queue session details fetch (with fallback)
            if is_celery_available():
                fetch_session_details.delay(session_id,
                                            force=force,
                                            debug=debug)
                logger.info(f"📋 Queued details fetch for: {session_id}")
            else:
                fetch_session_details(session_id=session_id,
                                      force=force,
                                      debug=debug)
                logger.info(f"📋 Processed details fetch for: {session_id}")

        except Exception as e:
            logger.error(f"❌ Error processing session row {i}: {e}")
            continue

    logger.info(
        f"🎉 Sessions processed: {created_count} created, {updated_count} updated"
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_details(self=None,
                          session_id=None,
                          force=False,
                          debug=False):
    """Fetch detailed information for a specific session."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Fetching details for session {session_id} in debug mode"
            )
            # Continue with actual API call in debug mode
        url = "https://open.assembly.go.kr/portal/openapi/VCONFDETAIL"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": format_conf_id(session_id)
        }

        logger.info(f"🔍 Fetching details for session: {session_id}")
        response = requests.get(url, params=params, timeout=30)

        response.raise_for_status()
        data = response.json()

        logger.info(
            f"📊 Session details API response structure: {list(data.keys()) if data else 'Empty response'}"
        )

        # Check for different possible response structures
        session_details = None
        if data.get('row') and len(data['row']) > 0:
            session_details = data['row'][0]
        elif 'VCONFDETAIL' in data and len(data['VCONFDETAIL']) > 1:
            # Handle nested structure like the sessions API
            session_details = data['VCONFDETAIL'][1].get('row', [])
            if session_details and len(session_details) > 0:
                session_details = session_details[0]
            else:
                session_details = None

        if not session_details:
            logger.info(
                f"ℹ️  No detailed info available for session {session_id} (this is normal for some sessions)"
            )
            if debug:
                logger.info(f"📋 Full API response: {data}")

            # Try to fetch bills anyway, some sessions might have bills without detailed info
            if is_celery_available():
                fetch_session_bills.delay(session_id, force=force, debug=debug)
            else:
                fetch_session_bills(session_id=session_id,
                                    force=force,
                                    debug=debug)
            return

        # Update session with detailed info if available
        session = Session.objects.get(conf_id=session_id)

        # Update session fields with detailed information
        if session_details.get('CONF_TIME'):
            try:
                # Parse time if available
                time_str = session_details.get('CONF_TIME', '09:00')
                session.bg_ptm = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                session.bg_ptm = dt_time(9, 0)  # Default time

        if session_details.get('ED_TIME'):
            try:
                time_str = session_details.get('ED_TIME', '18:00')
                session.ed_ptm = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                session.ed_ptm = dt_time(18, 0)  # Default time

        session.save()
        logger.info(f"✅ Updated session details for: {session_id}")

        # Queue bills fetch
        if is_celery_available():
            fetch_session_bills.delay(session_id, force=force, debug=debug)
        else:
            fetch_session_bills(session_id=session_id,
                                force=force,
                                debug=debug)

        # Queue PDF processing for statement extraction
        if session.down_url and not debug:
            if is_celery_available():
                process_session_pdf.delay(session_id, force=force, debug=debug)
            else:
                process_session_pdf(session_id=session_id,
                                    force=force,
                                    debug=debug)

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        f"Max retries exceeded for session {session_id}")
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        logger.error(f"❌ Error fetching session details for {session_id}: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self=None, session_id=None, force=False, debug=False):
    """Fetch bills for a specific session using VCONFBILLLIST API."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Fetching bills for session {session_id} in debug mode"
            )

        url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": format_conf_id(session_id)  # Zero-fill to 6 digits
        }

        logger.info(
            f"🔍 Fetching bills for session: {session_id} (formatted: {format_conf_id(session_id)})"
        )
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        logger.info(
            f"📊 Bills API response structure: {list(data.keys()) if data else 'Empty response'}"
        )

        if debug:
            logger.info(
                f"🐛 DEBUG: Full VCONFBILLLIST response: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        # Extract bills data from VCONFBILLLIST response structure
        bills_data = None
        if 'VCONFBILLLIST' in data and len(data['VCONFBILLLIST']) > 1:
            bills_data = data['VCONFBILLLIST'][1].get('row', [])
        elif 'VCONFBILLLIST' in data and len(data['VCONFBILLLIST']) > 0:
            # Check if first element has row data
            first_element = data['VCONFBILLLIST'][0]
            if 'row' in first_element:
                bills_data = first_element['row']
        elif 'row' in data:
            bills_data = data['row']

        print(response.text)

        if not bills_data:
            logger.info(f"ℹ️  No bills found for session {session_id}")
            if debug:
                logger.info(
                    f"🐛 DEBUG: Available data keys: {list(data.keys()) if data else 'None'}"
                )
                if 'VCONFBILLLIST' in data:
                    logger.info(
                        f"🐛 DEBUG: VCONFBILLLIST structure: {data['VCONFBILLLIST']}"
                    )
            return

        # Get session object
        try:
            session = Session.objects.get(conf_id=session_id)
        except Session.DoesNotExist:
            logger.error(f"❌ Session {session_id} not found in database")
            return

        created_count = 0
        updated_count = 0

        for bill_data in bills_data:
            try:
                bill_id = bill_data.get('BILL_ID')
                if not bill_id:
                    continue

                bill, created = Bill.objects.get_or_create(
                    bill_id=bill_id,
                    defaults={
                        'session': session,
                        'bill_nm': bill_data.get('BILL_NM', ''),
                        'link_url': bill_data.get('LINK_URL', '')
                    })

                if created:
                    created_count += 1
                    logger.info(f"✨ Created new bill: {bill_id}")
                elif force:
                    # Update existing bill if force is True
                    bill.bill_nm = bill_data.get('BILL_NM', bill.bill_nm)
                    bill.link_url = bill_data.get('LINK_URL', bill.link_url)
                    bill.save()
                    updated_count += 1
                    logger.info(f"🔄 Updated existing bill: {bill_id}")

                if debug:
                    logger.info(
                        f"🐛 DEBUG: Processed bill - ID: {bill_id}, Name: {bill_data.get('BILL_NM', '')[:50]}..."
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error processing bill {bill_data.get('BILL_ID', 'unknown')}: {e}"
                )
                continue

        logger.info(
            f"🎉 Bills processed for session {session_id}: {created_count} created, {updated_count} updated"
        )

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        f"Max retries exceeded for bills fetch {session_id}")
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        logger.error(f"❌ Error fetching bills for session {session_id}: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self=None, session_id=None, force=False, debug=False):
    """Download and process PDF transcript for a session to extract statements."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Processing PDF for session {session_id} in debug mode"
            )

        # Get session object
        try:
            session = Session.objects.get(conf_id=session_id)
        except Session.DoesNotExist:
            logger.error(f"❌ Session {session_id} not found in database")
            return

        if not session.down_url:
            logger.info(f"ℹ️  No PDF URL available for session {session_id}")
            return

        logger.info(f"📄 Processing PDF for session: {session_id}")

        # Download PDF
        response = requests.get(session.down_url, timeout=60, stream=True)
        response.raise_for_status()

        # Save PDF temporarily
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        temp_pdf_path = temp_dir / f"temp_{session_id}.pdf"

        with open(temp_pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"📥 Downloaded PDF for session {session_id}")

        # Extract text from PDF
        try:
            with pdfplumber.open(temp_pdf_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"

                logger.info(
                    f"📄 Extracted {len(full_text)} characters from PDF")

                # Fetch bill context for the session
                bills_context = get_bills_context(session_id)

                # Process the extracted text using the helper function
                process_pdf_statements(full_text, session_id, session,
                                       bills_context, debug)

        except Exception as e:
            logger.error(
                f"❌ Error extracting text from PDF for session {session_id}: {e}"
            )
            return
        finally:
            # Clean up temporary file
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()

    except Exception as e:
        if isinstance(e, RequestException):
            if self:
                try:
                    self.retry(exc=e)
                except MaxRetriesExceededError:
                    logger.error(
                        f"Max retries exceeded for PDF processing {session_id}"
                    )
                    raise
            else:
                logger.error("Sync execution failed, no retry available")
                raise
        logger.error(f"❌ Error processing PDF for session {session_id}: {e}")
        raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_statement_categories(self=None, statement_id=None):
    """Analyze categories and sentiment for an existing statement using LLM."""
    if not model:
        logger.warning("❌ Gemini model not available for statement analysis")
        return

    try:
        from .models import Statement
        statement = Statement.objects.get(id=statement_id)

        prompt = f"""
다음 국회 발언을 분석하여 감성 분석과 정책 분류를 수행해주세요.

발언자: {statement.speaker.naas_nm}
발언 내용: {statement.text}

다음 JSON 형식으로 분석 결과를 제공해주세요:
{{
    "sentiment_score": -1부터 1까지의 감성 점수 (숫자),
    "sentiment_reason": "감성 분석 근거",
    "policy_categories": [
        {{
            "main_category": "주요 정책 분야 (경제, 사회복지, 교육, 외교안보, 환경, 법무, 과학기술, 문화체육, 농림축산, 국정감사 중 하나)",
            "sub_category": "세부 분야",
            "confidence": 0부터 1까지의 확신도 (숫자)
        }}
    ],
    "policy_keywords": ["정책 관련 주요 키워드들"]
}}

분석 기준:
1. 감성 분석: -1(매우 부정적) ~ 1(매우 긍정적)
2. 정책 분류: 발언 내용을 기반으로 관련 정책 분야 분류
3. 주요 키워드: 정책과 관련된 핵심 용어들 추출

응답은 반드시 유효한 JSON 형식이어야 합니다.
"""

        response = model.generate_content(prompt)

        if not response.text:
            logger.warning(
                f"❌ No response from LLM for statement {statement_id}")
            return

        # Clean the response text
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        # Parse JSON response
        import json as json_module
        analysis_data = json_module.loads(response_text)

        # Update statement with analysis results
        statement.sentiment_score = analysis_data.get('sentiment_score', 0.0)
        statement.sentiment_reason = analysis_data.get('sentiment_reason',
                                                       'LLM 분석 완료')
        statement.policy_keywords = ', '.join(
            analysis_data.get('policy_keywords', []))
        statement.category_analysis = json.dumps(analysis_data.get(
            'policy_categories', []),
                                                 ensure_ascii=False)
        statement.save()

        # Create category associations
        policy_categories = analysis_data.get('policy_categories', [])
        if policy_categories:
            create_statement_categories(statement, policy_categories)

        logger.info(
            f"✅ Analyzed statement {statement_id}: sentiment={statement.sentiment_score}, categories={len(policy_categories)}"
        )

    except json.JSONDecodeError as e:
        logger.error(
            f"❌ Failed to parse LLM JSON response for statement {statement_id}: {e}"
        )
        logger.error(f"❌ Response parsing failed - check LLM output format")
    except Exception as e:
        logger.error(f"❌ Error analyzing statement {statement_id}: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for statement analysis {statement_id}"
                )
                raise

    except Exception as e:
        logger.error(f"❌ Error analyzing statement {statement_id}: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for statement analysis {statement_id}"
                )
                raise


def process_pdf_statements(full_text,
                           session_id,
                           session,
                           bills_context,
                           debug=False):
    """Helper function to process PDF statements."""
    try:
        # Skip processing if no LLM available
        if not model:
            logger.warning(
                "❌ LLM not available, skipping statement extraction")
            return

        # Parse and analyze statements from text using LLM
        statements_data = extract_statements_with_llm_validation(
            full_text, session_id, bills_context, debug)

        # Process extracted and analyzed statements
        created_count = 0
        for statement_data in statements_data:
            try:
                speaker_name = statement_data.get('speaker_name', '').strip()
                statement_text = statement_data.get('text', '').strip()
                sentiment_score = statement_data.get('sentiment_score', 0.0)
                sentiment_reason = statement_data.get('sentiment_reason',
                                                      'LLM 분석 완료')
                policy_categories = statement_data.get('policy_categories', [])
                policy_keywords = statement_data.get('policy_keywords', [])

                if not speaker_name or not statement_text:
                    logger.warning(
                        f"⚠️ Skipping statement with missing speaker or text")
                    continue

                # Refresh database connection before processing
                from django.db import connection
                connection.ensure_connection()

                # Get or create speaker
                speaker = get_or_create_speaker(speaker_name, debug)
                if not speaker:
                    logger.warning(
                        f"⚠️ Could not create speaker: {speaker_name}")
                    continue

                # Check if statement already exists to avoid duplicates
                existing_statement = Statement.objects.filter(
                    session=session, speaker=speaker,
                    text=statement_text).first()

                if existing_statement:
                    logger.info(
                        f"ℹ️ Statement already exists for {speaker_name}")
                    continue

                # Create statement with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        statement = Statement.objects.create(
                            session=session,
                            speaker=speaker,
                            text=statement_text,
                            sentiment_score=sentiment_score,
                            sentiment_reason=sentiment_reason,
                            policy_keywords=', '.join(policy_keywords)
                            if policy_keywords else '',
                            category_analysis=json.dumps(policy_categories,
                                                         ensure_ascii=False)
                            if policy_categories else '')

                        created_count += 1
                        logger.info(
                            f"✨ Created statement for {speaker_name} with sentiment {sentiment_score}: {statement_text[:50]}..."
                        )

                        # Create category associations if available
                        if policy_categories and not debug:
                            create_statement_categories(
                                statement, policy_categories)

                        break

                    except Exception as db_error:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️ Database error on attempt {attempt + 1}, retrying: {db_error}"
                            )
                            # Close and reconnect database connection
                            connection.close()
                            time.sleep(1)  # Brief delay before retry
                            continue
                        else:
                            raise db_error

            except Exception as e:
                logger.error(f"❌ Error creating statement: {e}")
                logger.error(f"❌ Statement data: {statement_data}")
                continue

        logger.info(
            f"🎉 Processed PDF for session {session_id}: {created_count} statements created"
        )

    except Exception as e:
        logger.error(
            f"❌ Error processing PDF statements for session {session_id}: {e}")
        raise


def extract_statements_with_llm_validation(text,
                                           session_id,
                                           bills_context,
                                           debug=False):
    """Extract statements using two-stage LLM approach: speaker detection + content analysis."""

    if not model:
        logger.warning(
            "❌ LLM model not available, falling back to regex extraction")
        return extract_statements_with_regex_fallback(text, session_id, debug)

    logger.info(
        f"🤖 Starting two-stage LLM extraction for session: {session_id}")

    try:
        # Configure lighter model for speaker detection
        speaker_detection_model = genai.GenerativeModel(
            'gemini-2.0-flash-lite')

        # Stage 1: Speaker Detection and Boundary Identification
        logger.info(
            f"🔍 Stage 1: Detecting speakers and speech boundaries (session: {session_id})"
        )

        speaker_detection_prompt = f"""
당신은 기록가입니다. 당신의 기록은 미래에 사람들을 살릴 것이므로, 발언 구간을 하나도 빠뜨리면 안 됩니다. 다음은 국회 회의록 텍스트입니다. 이 텍스트에서 실제 국회의원들의 발언 구간을 정확히 식별해주세요.

회의 관련 의안:
{bills_context}

회의록 텍스트:
{text}

다음 기준으로 발언을 식별해주세요:
1. ◯ 기호로 시작하는 발언만 추출
2. 실제 사람 이름(국회의원)만 포함, 법률명이나 기관명 제외
3. 절차적 발언(투표, 개회, 폐회 등)은 제외
4. 최소 50자 이상의 의미있는 정책 토론 내용만 포함

JSON 형식으로 응답해주세요:
{{
    "speakers_detected": [
        {{
            "speaker_name": "발언자 실명",
            "start_marker": "발언 시작 부분 텍스트 (20자)",
            "end_marker": "발언 종료 부분 텍스트 (20자)",
            "is_substantial": true/false,
            "speech_type": "policy_discussion/procedural/other"
        }}
    ]
}}
"""

        stage1_response = speaker_detection_model.generate_content(
            speaker_detection_prompt)

        if not stage1_response.text:
            logger.warning(
                "❌ No response from Stage 1 LLM, falling back to regex")
            return extract_statements_with_regex_fallback(
                text, session_id, debug)

        # Parse Stage 1 response
        stage1_text = stage1_response.text.strip()
        logger.info(f"🔍 Raw Stage 1 response: {stage1_text[:500]}...")

        if stage1_text.startswith('```json'):
            stage1_text = stage1_text[7:-3].strip()
        elif stage1_text.startswith('```'):
            stage1_text = stage1_text[3:-3].strip()

        logger.info(f"🔍 Cleaned Stage 1 response: {stage1_text[:500]}...")

        import json as json_module
        stage1_data = json_module.loads(stage1_text)
        speakers_detected = stage1_data.get('speakers_detected', [])

        logger.info(f"🔍 Parsed speakers_detected: {speakers_detected}")

        for i, speaker in enumerate(speakers_detected):
            logger.info(f"🔍 Speaker {i+1} details: {speaker}")

        logger.info(
            f"✅ Stage 1 completed: Found {len(speakers_detected)} potential speakers"
        )

        # Stage 2: Extract and analyze substantial policy discussions
        logger.info(
            f"🔍 Stage 2: Extracting and analyzing policy content (session: {session_id})"
        )

        analyzed_statements = []

        for i, speaker_info in enumerate(speakers_detected, 1):
            speaker_name = speaker_info.get('speaker_name', 'Unknown')
            is_substantial = speaker_info.get('is_substantial', False)
            speech_type = speaker_info.get('speech_type', 'unknown')

            logger.info(f"🔍 Processing speaker {i}: {speaker_name}")
            logger.info(f"   - is_substantial: {is_substantial}")
            logger.info(f"   - speech_type: {speech_type}")

            if not is_substantial or speech_type != 'policy_discussion':
                logger.info(
                    f"⚠️ Skipping speaker {speaker_name} - substantial: {is_substantial}, type: {speech_type}"
                )
                continue

            # Extract the actual speech content using markers
            start_marker = speaker_info.get('start_marker', '')
            end_marker = speaker_info.get('end_marker', '')

            logger.info(f"🔍 Extracting speech for {speaker_name}")
            logger.info(f"   - start_marker: '{start_marker[:50]}...'")
            logger.info(f"   - end_marker: '{end_marker[:50]}...'")

            # Find speech content between markers
            speech_content = extract_speech_between_markers(
                text, start_marker, end_marker, speaker_name)

            logger.info(
                f"   - extracted length: {len(speech_content) if speech_content else 0}"
            )
            if speech_content:
                logger.info(
                    f"   - content preview: '{speech_content[:100]}...'")

            if not speech_content or len(speech_content) < 10:
                logger.info(
                    f"⚠️ Skipping {speaker_name} - insufficient content (length: {len(speech_content) if speech_content else 0})"
                )
                continue

            logger.info(
                f"🤖 Analyzing statement {i}/{len(speakers_detected)} from {speaker_name} (session: {session_id})"
            )

            # Stage 2: Analyze the extracted speech
            analysis_result = analyze_single_statement(
                {
                    'speaker_name': speaker_name,
                    'text': speech_content
                }, session_id, debug)

            analyzed_statements.append(analysis_result)

            # Brief pause between API calls
            if not debug:
                time.sleep(0.5)

        logger.info(
            f"✅ Two-stage LLM extraction completed: {len(analyzed_statements)} statements (session: {session_id})"
        )
        return analyzed_statements

    except Exception as e:
        logger.error(f"❌ Error in two-stage LLM extraction: {e}")
        logger.info("⚠️  Falling back to regex extraction")
        return extract_statements_with_regex_fallback(text, session_id, debug)


def extract_speech_between_markers(text, start_marker, end_marker,
                                   speaker_name):
    """Extract speech content between start and end markers."""
    try:
        # Find the start position
        start_pos = text.find(start_marker)
        if start_pos == -1:
            # Try to find by speaker pattern as fallback
            speaker_pattern = f"◯{speaker_name}"
            start_pos = text.find(speaker_pattern)
            if start_pos == -1:
                return ""

        # Find the end position
        end_pos = text.find(end_marker, start_pos + len(start_marker))
        if end_pos == -1:
            # Find next speaker as fallback
            next_speaker_pos = text.find("◯", start_pos + len(start_marker))
            if next_speaker_pos != -1:
                end_pos = next_speaker_pos
            else:
                end_pos = len(text)

        # Extract content
        content = text[start_pos:end_pos].strip()

        # Clean up the content
        # Remove speaker name from beginning
        if content.startswith(f"◯{speaker_name}"):
            content = content[len(f"◯{speaker_name}"):].strip()

        # Remove parenthetical notes and clean whitespace
        import re
        content = re.sub(r'\([^)]*\)', '', content)
        content = re.sub(r'\s+', ' ', content).strip()

        return content

    except Exception as e:
        logger.error(f"❌ Error extracting speech content: {e}")
        return ""


def extract_statements_with_regex_fallback(text, session_id, debug=False):
    """Fallback regex extraction method (existing implementation)."""
    import re

    logger.info(
        f"📄 Extracting statements using regex fallback (session: {session_id})"
    )

    # Clean up the text first
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s+', ' ', text)

    statements = []
    speaker_pattern = r'◯([^◯\n]+?)\s+([^◯]+?)(?=◯|$)'
    matches = re.findall(speaker_pattern, text, re.DOTALL | re.MULTILINE)

    for speaker_raw, content_raw in matches:
        speaker_name = speaker_raw.strip()
        speaker_name = re.sub(
            r'\s*(의원|위원장|장관|국장|의장|부의장|차관|실장|국무총리|대통령|부총리)\s*', '',
            speaker_name).strip()

        if not speaker_name or not content_raw.strip():
            continue

        # Enhanced filtering for non-person entities
        role_patterns = [
            r'.*대리$', r'^의사$', r'^위원장$', r'.*위원회.*', r'.*부.*장관.*', r'.*청장.*',
            r'.*실장.*', r'^사회자$', r'^진행자$', r'.*개정법률안.*', r'.*특별법.*',
            r'.*진흥법.*', r'.*관리법.*', r'.*촉진법.*', r'.*보호법.*', r'.*법률.*', r'.*법$',
            r'.*육성.*', r'.*지원.*', r'^재난$', r'^인구감소지역$', r'^우주개발$',
            r'^여성과학기술인$', r'.*기획재정부.*', r'.*총장\([^)]+\).*', r'^탄소소재$',
            r'^전기공사업법$', r'^특허법$', r'.*소재$', r'.*업법$', r'겸.*부$'
        ]

        korean_surname_pattern = r'^[김이박최정강조윤장임한오서신권황안송류전고문양손배백허남심노정하곽성차주우구신임나전민유진지엄채원천방공강현함변염양변홍]'

        is_role = any(
            re.match(pattern, speaker_name) for pattern in role_patterns)
        is_likely_person = (
            re.match(korean_surname_pattern, speaker_name)
            and 2 <= len(speaker_name) <= 4
            and not any(char in speaker_name
                        for char in ['(', ')', '법', '부', '청', '원회', '관', '장']))

        if is_role or not is_likely_person:
            if debug:
                logger.info(
                    f"🐛 DEBUG: Skipping non-person speaker: {speaker_name}")
            continue

        content = content_raw.strip()
        content = re.sub(r'\([^)]*\)', '', content)
        content = re.sub(r'\s+', ' ', content).strip()

        if len(content) < 100:
            continue

        # Check for procedural content
        procedural_phrases = [
            '투표해 주시기 바랍니다', '투표를 마치겠습니다', '가결되었음을 선포합니다', '수고하셨습니다', '상정합니다',
            '의결하도록 하겠습니다', '원안가결되었음을 선포합니다', '폐회를 선포합니다', '개회를 선포합니다',
            '회의를 시작하겠습니다'
        ]

        is_procedural = any(phrase in content for phrase in procedural_phrases)
        if is_procedural:
            continue

        policy_indicators = [
            '법률안', '개정', '제안', '필요', '문제', '개선', '정책', '방안', '대책', '예산', '추진',
            '계획', '검토', '의견', '생각', '판단', '국민', '시민', '사회', '경제', '정치', '교육',
            '복지', '환경'
        ]

        has_policy_content = any(indicator in content
                                 for indicator in policy_indicators)
        if len(content) > 200 or has_policy_content:
            statements.append({'speaker_name': speaker_name, 'text': content})

    logger.info(
        f"✅ Regex fallback completed: {len(statements)} statements (session: {session_id})"
    )
    return statements


def analyze_single_statement(statement_data, session_id, debug=False):
    """Analyze a single statement using LLM."""
    if not model:
        logger.warning("❌ LLM model not available for statement analysis")
        return statement_data

    speaker_name = statement_data.get('speaker_name', '')
    text = statement_data.get('text', '')

    prompt = f"""
다음 국회 발언을 분석하여 감성 분석과 정책 분류를 수행해주세요.

발언자: {speaker_name}
발언 내용: {text}

다음 JSON 형식으로 분석 결과를 제공해주세요:
{{
    "sentiment_score": -1부터 1까지의 감성 점수 (숫자),
    "sentiment_reason": "감성 분석 근거",
    "policy_categories": [
        {{
            "main_category": "주요 정책 분야 (경제, 사회복지, 교육, 외교안보, 환경, 법무, 과학기술, 문화체육, 농림축산, 국정감사 중 하나)",
            "sub_category": "세부 분야",
            "confidence": 0부터 1까지의 확신도 (숫자)
        }}
    ],
    "policy_keywords": ["정책 관련 주요 키워드들"]
}}

분석 기준:
1. 감성 분석: -1(매우 부정적) ~ 1(매우 긍정적)
2. 정책 분류: 발언 내용을 기반으로 관련 정책 분야 분류
3. 주요 키워드: 정책과 관련된 핵심 용어들 추출

응답은 반드시 유효한 JSON 형식이어야 합니다.
"""

    try:
        response = model.generate_content(prompt)

        if not response.text:
            logger.warning(
                f"❌ No LLM response for statement from {speaker_name}")
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
            'sentiment_score':
            analysis_data.get('sentiment_score', 0.0),
            'sentiment_reason':
            analysis_data.get('sentiment_reason', 'LLM 분석 완료'),
            'policy_categories':
            analysis_data.get('policy_categories', []),
            'policy_keywords':
            analysis_data.get('policy_keywords', [])
        })

        if debug:
            logger.info(
                f"🐛 DEBUG: Analyzed statement from {speaker_name} - Sentiment: {statement_data.get('sentiment_score', 0)}"
            )

        return statement_data

    except Exception as e:
        logger.error(f"❌ Error analyzing statement from {speaker_name}: {e}")
        return statement_data


def get_bills_context(session_id):
    """Fetch bill context for a session to provide LLM."""
    try:
        session = Session.objects.get(conf_id=session_id)
        bills = Bill.objects.filter(session=session)

        bill_names = [bill.bill_nm for bill in bills]
        return ", ".join(bill_names)
    except Exception as e:
        logger.error(f"❌ Error fetching bills context: {e}")
        return ""


def parse_and_analyze_statements_from_text(text,
                                           session_id,
                                           bills_context,
                                           debug=False):
    """Parse statements from PDF text using regex, then analyze each individually."""
    # Step 1: Extract statements using regex
    statements = extract_statements_with_llm_validation(
        text, session_id, bills_context, debug)

    if not statements:
        logger.warning(
            f"❌ No statements extracted from PDF (session: {session_id})")
        return []

    # Step 2: Analyze each statement individually
    analyzed_statements = []
    for i, statement in enumerate(statements, 1):
        logger.info(
            f"🤖 Analyzing statement {i}/{len(statements)} from {statement.get('speaker_name', 'Unknown')} (session: {session_id})"
        )

        analyzed_statement = analyze_single_statement(statement, session_id,
                                                      debug)
        analyzed_statements.append(analyzed_statement)

        # Brief pause between API calls to avoid rate limiting
        if not debug:
            time.sleep(0.5)

    logger.info(
        f"✅ Completed analysis of {len(analyzed_statements)} statements (session: {session_id})"
    )

    return analyzed_statements


def create_statement_categories(statement, policy_categories):
    """Create category associations for a statement based on LLM analysis."""
    try:
        from .models import Category, Subcategory, StatementCategory

        for category_data in policy_categories:
            main_category = category_data.get('main_category', '').strip()
            sub_category = category_data.get('sub_category', '').strip()
            confidence = category_data.get('confidence', 0.0)

            if not main_category:
                continue

            # Get or create main category
            category, created = Category.objects.get_or_create(
                name=main_category,
                defaults={'description': f'{main_category} 관련 정책'})

            # Get or create subcategory if provided
            subcategory = None
            if sub_category:
                subcategory, created = Subcategory.objects.get_or_create(
                    name=sub_category,
                    category=category,
                    defaults={'description': f'{sub_category} 관련 세부 정책'})

            # Create statement category association
            StatementCategory.objects.get_or_create(
                statement=statement,
                category=category,
                subcategory=subcategory,
                defaults={'confidence_score': confidence})

        logger.info(
            f"✅ Created {len(policy_categories)} category associations for statement {statement.id}"
        )

    except Exception as e:
        logger.error(f"❌ Error creating statement categories: {e}")


def get_or_create_speaker(speaker_name, debug=False):
    """Get or create speaker by name."""
    if not speaker_name:
        return None

    # Clean speaker name
    speaker_name = speaker_name.replace('의원',
                                        '').replace('위원장',
                                                    '').replace('장관',
                                                                '').strip()

    try:
        # Ensure database connection
        from django.db import connection
        connection.ensure_connection()

        # Try to find existing speaker
        speaker = Speaker.objects.filter(
            naas_nm__icontains=speaker_name).first()

        if not speaker:
            # Create temporary speaker record with fallback values for all fields
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    speaker = Speaker.objects.create(
                        naas_cd=f"TEMP_{speaker_name}_{int(time.time())}",
                        naas_nm=speaker_name,
                        naas_ch_nm="정보 없음",
                        plpt_nm="정당정보없음",
                        elecd_nm="정보 없음",
                        elecd_div_nm="정보 없음",
                        cmit_nm="정보 없음",
                        blng_cmit_nm="정보 없음",
                        rlct_div_nm="정보 없음",
                        gtelt_eraco="정보 없음",
                        ntr_div="정보 없음",
                        naas_pic="")

                    if debug:
                        logger.info(
                            f"🐛 DEBUG: Created temporary speaker: {speaker_name}"
                        )

                    # Queue detailed speaker fetch
                    if not debug:
                        fetch_speaker_details(speaker_name)
                    break

                except Exception as db_error:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"⚠️ Database error creating speaker on attempt {attempt + 1}: {db_error}"
                        )
                        connection.close()
                        time.sleep(1)
                        continue
                    else:
                        logger.error(
                            f"❌ Failed to create speaker after {max_retries} attempts: {db_error}"
                        )
                        return None

        return speaker

    except Exception as e:
        logger.error(f"❌ Error in get_or_create_speaker: {e}")
        return None


# Note: Sentiment analysis is now integrated into the comprehensive statement analysis above


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
        logger.error(f"❌ Error fetching from nepjpxkkabqiqpbvk API: {e}")
        raise
