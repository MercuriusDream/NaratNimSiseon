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
        statements_data = []
        try:
            with pdfplumber.open(temp_pdf_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"

                logger.info(f"📄 Extracted {len(full_text)} characters from PDF")

                # Skip processing if no LLM available
                if not model:
                    logger.warning("❌ LLM not available, skipping statement extraction")
                    return

                # Parse statements from text using LLM
                statements_data = parse_statements_from_text(
                    full_text, session_id, debug)

        except Exception as e:
            logger.error(f"❌ Error extracting text from PDF {session_id}: {e}")
            return
        finally:
            # Clean up temporary file
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()

        # Process extracted statements
        created_count = 0
        for statement_data in statements_data:
            try:
                speaker_name = statement_data.get('speaker_name', '').strip()
                statement_text = statement_data.get('text', '').strip()
                
                if not speaker_name or not statement_text:
                    logger.warning(f"⚠️ Skipping statement with missing speaker or text")
                    continue

                # Get or create speaker
                speaker = get_or_create_speaker(speaker_name, debug)
                if not speaker:
                    logger.warning(f"⚠️ Could not create speaker: {speaker_name}")
                    continue

                # Check if statement already exists to avoid duplicates
                existing_statement = Statement.objects.filter(
                    session=session,
                    speaker=speaker,
                    text=statement_text
                ).first()

                if existing_statement and not force:
                    logger.info(f"ℹ️ Statement already exists for {speaker_name}")
                    continue

                # Create statement
                statement = Statement.objects.create(
                    session=session,
                    speaker=speaker,
                    text=statement_text,
                    sentiment_score=0.0,  # Will be analyzed later
                    sentiment_reason="Pending analysis")

                created_count += 1
                logger.info(f"✨ Created statement for {speaker_name}: {statement_text[:50]}...")

                # Queue sentiment analysis if LLM is available
                if model and not debug:
                    analyze_statement_sentiment.delay(statement.id)

            except Exception as e:
                logger.error(f"❌ Error creating statement: {e}")
                logger.error(f"❌ Statement data: {statement_data}")
                continue

        logger.info(
            f"🎉 Processed PDF for session {session_id}: {created_count} statements created"
        )

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


def parse_statements_from_text(text, session_id, debug=False):
    """Parse statements from PDF text content using LLM."""
    if not model:
        logger.warning("❌ LLM model not available for statement parsing")
        return []

    # Truncate text if it's too long (keep first 50000 characters)
    if len(text) > 50000:
        text = text[:50000] + "...[텍스트 생략]"
        logger.info(f"📄 Truncated PDF text to 50000 characters for LLM processing")

    prompt = f"""
다음은 국회 회의록 PDF에서 추출한 텍스트입니다. 이 텍스트를 분석하여 각 발언자의 발언을 구조화된 형태로 추출해주세요.

회의록 텍스트:
{text}

다음 JSON 형식으로 발언들을 추출해주세요:
{{
    "statements": [
        {{
            "speaker_name": "발언자명 (의원, 위원장, 장관 등의 직책 제외)",
            "text": "발언 내용 전체"
        }}
    ]
}}

주의사항:
1. 발언자명에서 "의원", "위원장", "장관" 등의 직책은 제거하고 이름만 추출
2. 각 발언의 완전한 내용을 포함
3. 절차적 발언이나 형식적 문구는 제외
4. 실질적인 정책 발언만 포함
5. 발언자가 명확하지 않은 경우 제외

응답은 반드시 유효한 JSON 형식이어야 합니다.
"""

    try:
        logger.info(f"🤖 Sending PDF text to LLM for statement extraction (session: {session_id})")
        response = model.generate_content(prompt)
        
        if not response.text:
            logger.warning(f"❌ No response from LLM for session {session_id}")
            return []

        # Clean the response text
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()

        # Parse JSON response
        import json
        parsed_response = json.loads(response_text)
        statements = parsed_response.get('statements', [])

        logger.info(f"✅ LLM extracted {len(statements)} statements from PDF (session: {session_id})")
        
        if debug:
            logger.info(f"🐛 DEBUG: LLM extracted {len(statements)} statements")
            for i, stmt in enumerate(statements[:3], 1):  # Show first 3
                logger.info(
                    f"🐛 DEBUG Statement {i}: {stmt.get('speaker_name', 'Unknown')[:20]}... - {stmt.get('text', '')[:50]}..."
                )

        return statements

    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse LLM JSON response for session {session_id}: {e}")
        logger.error(f"❌ Raw LLM response: {response.text[:500]}...")
        return []
    except Exception as e:
        logger.error(f"❌ Error using LLM for statement extraction (session {session_id}): {e}")
        return []


def get_or_create_speaker(speaker_name, debug=False):
    """Get or create speaker by name."""
    if not speaker_name:
        return None

    # Clean speaker name
    speaker_name = speaker_name.replace('의원',
                                        '').replace('위원장',
                                                    '').replace('장관',
                                                                '').strip()

    # Try to find existing speaker
    speaker = Speaker.objects.filter(naas_nm__icontains=speaker_name).first()

    if not speaker:
        # Create temporary speaker record
        speaker = Speaker.objects.create(
            naas_cd=f"TEMP_{speaker_name}_{int(time.time())}",
            naas_nm=speaker_name,
            plpt_nm="정당정보없음")

        if debug:
            logger.info(f"🐛 DEBUG: Created temporary speaker: {speaker_name}")

        # Queue detailed speaker fetch
        if not debug:
            fetch_speaker_details(speaker_name)

    return speaker


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_statement_sentiment(self=None, statement_id=None):
    """Analyze sentiment of a statement using LLM."""
    if not model:
        logger.warning("❌ Gemini model not available for sentiment analysis")
        return

    try:
        statement = Statement.objects.get(id=statement_id)

        prompt = f"""
        다음 국회 발언의 감성을 분석해주세요. -1(매우 부정적)부터 1(매우 긍정적)까지의 점수와 근거를 제공해주세요.

        발언 내용: {statement.text[:1000]}

        응답 형식:
        점수: [숫자]
        근거: [분석 근거]
        """

        response = model.generate_content(prompt)

        # Parse response
        sentiment_score = 0.0
        sentiment_reason = "분석 완료"

        if response.text:
            lines = response.text.strip().split('\n')
            for line in lines:
                if line.startswith('점수:'):
                    try:
                        sentiment_score = float(line.split(':')[1].strip())
                    except:
                        pass
                elif line.startswith('근거:'):
                    sentiment_reason = line.split(':', 1)[1].strip()

        # Update statement
        statement.sentiment_score = sentiment_score
        statement.sentiment_reason = sentiment_reason
        statement.save()

        logger.info(
            f"✅ Analyzed sentiment for statement {statement_id}: {sentiment_score}"
        )

    except Exception as e:
        logger.error(
            f"❌ Error analyzing sentiment for statement {statement_id}: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for sentiment analysis {statement_id}"
                )


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
