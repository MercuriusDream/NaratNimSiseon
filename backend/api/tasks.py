import requests
import pdfplumber
from celery import shared_task
from django.conf import settings
from .models import Session, Bill, Speaker, Statement  # Assuming these models are correctly defined
from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import RequestException
import logging
from celery.schedules import crontab  # Keep if you plan to use Celery Beat schedules
from datetime import datetime, timedelta, time as dt_time
import json
import os  # Keep if used elsewhere or for future Path handling consistency
import time
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures
import queue

logger = logging.getLogger(__name__)


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
                    psycopg2.OperationalError) as e:
                error_msg = str(e).lower()
                is_connection_error = any(phrase in error_msg for phrase in [
                    'connection already closed',
                    'server closed the connection',
                    'ssl connection has been closed', 'connection lost',
                    'connection broken', 'server has gone away',
                    'connection timeout'
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

# Configure Gemini API with error handling
try:
    import google.generativeai as genai
    if hasattr(settings, 'GEMINI_API_KEY') and settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            'gemma-3-27b-it')  # Main model for detailed analysis
    else:
        logger.warning(
            "GEMINI_API_KEY not found or empty in settings. LLM features will be disabled."
        )
        genai = None
        model = None
except ImportError:
    logger.warning(
        "google.generativeai library not available. LLM features will be disabled."
    )
    genai = None
    model = None
except Exception as e:
    logger.warning(
        f"Error configuring Gemini API: {e}. LLM features will be disabled.")
    genai = None
    model = None


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
    """Format CONF_ID to be zero-filled to 6 digits."""
    return str(conf_id).zfill(6)


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
                result_code_info = head_info[0].get('RESULT',
                                                    {}).get('CODE', 'UNKNOWN')
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
                        if debug and sessions_data_list:
                            logger.debug(
                                "Extracted data from data['{api_key_name}'][0]['row'] despite head info code."
                            )

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


def process_sessions_data(sessions_data, force=False, debug=False):
    """Process the sessions data and create/update session objects"""
    if not sessions_data:
        logger.info("No sessions data provided to process.")
        return

    from django.db import connection

    @with_db_retry
    def _process_session_item(session_defaults, confer_num):
        return Session.objects.update_or_create(conf_id=confer_num,
                                                defaults=session_defaults)

    # Group by CONFER_NUM (session_id) as multiple agenda items can be part of the same physical session meeting
    sessions_by_confer_num = {}
    for item_data in sessions_data:
        confer_num = item_data.get('CONFER_NUM')
        if not confer_num:
            logger.warning(
                f"Skipping item due to missing CONFER_NUM: {item_data.get('TITLE', 'N/A')}"
            )
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
        # Ensure connection is still alive for each session
        connection.ensure_connection()

        # Use the first item for primary session details, assuming they are consistent for the same CONFER_NUM
        main_item = items_for_session[0]
        try:
            session_title = main_item.get('TITLE', '제목 없음')
            logger.info(
                f"Processing session ID {confer_num}: {session_title} ({len(items_for_session)} items)"
            )

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
                            f"Could not parse date: {conf_date_str} for session {confer_num}. Skipping date."
                        )

            # Extract DAE_NUM, SESS, DGR from TITLE (example: 제22대국회 제400회국회(정기회) 제01차)
            # This parsing is brittle. If API provides these fields separately, use them.
            era_co_val = f"제{main_item.get('DAE_NUM', 'N/A')}대"  # Prefer direct DAE_NUM field
            sess_val = ''
            dgr_val = ''
            title_parts = session_title.split(' ')
            # Example parsing logic - highly dependent on fixed title format
            if len(title_parts
                   ) > 1 and "회국회" in title_parts[1]:  # e.g. 제400회국회(정기회)
                sess_val = title_parts[1].split('회국회')[0]  # 400
                if "(" in sess_val:
                    sess_val = sess_val.split("(")[0]  # clean (정기회)
            if len(title_parts) > 2 and "차" in title_parts[2]:  # e.g. 제01차
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
                main_item.get('CLASS_NAME', '국회본회의'),  # Or COMMITTEE_NAME
                'cmit_nm':
                main_item.get('CMIT_NAME', main_item.get(
                    'CLASS_NAME', '국회본회의')),  # Prefer CMIT_NAME if available
                'down_url':
                main_item.get('PDF_LINK_URL', ''),
                'title':
                session_title,  # Store the full title
                # bg_ptm might come from VCONFDETAIL, initialize if not set
                'bg_ptm':
                dt_time(9, 0)  # Default, can be updated later
            }

            if debug:
                logger.debug(
                    f"🐛 DEBUG: Session {confer_num} defaults for DB: {session_defaults}"
                )
                logger.info(
                    f"🐛 DEBUG PREVIEW: Would process session ID {confer_num}: {session_title}"
                )
                continue  # Skip database operations in debug mode for this part

            # Use retry wrapper for database operations
            session_obj, created = _process_session_item(
                session_defaults, confer_num)

            if created:
                created_count += 1
                logger.info(
                    f"✨ Created new session: {confer_num} - {session_title}")
            else:
                if force:  # If not created but force is true, it implies update_or_create updated it.
                    updated_count += 1
                    logger.info(
                        f"🔄 Updated existing session: {confer_num} - {session_title}"
                    )
                else:
                    logger.info(
                        f"♻️ Session already exists and not in force mode: {confer_num}"
                    )

            # Regardless of created/updated, try to fetch more details
            # Call for details which then calls for bills and PDF
            if is_celery_available():
                fetch_session_details.delay(session_id=confer_num,
                                            force=force,
                                            debug=debug)
            else:
                fetch_session_details(session_id=confer_num,
                                      force=force,
                                      debug=debug)

        except Exception as e:
            logger.error(
                f"❌ Error processing session data for CONFER_NUM {confer_num} (Title: {main_item.get('TITLE', 'N/A')}): {e}"
            )
            logger.exception("Full traceback for session processing error:")
            continue

    logger.info(
        f"🎉 Sessions processing complete: {created_count} created, {updated_count} updated."
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_details(self,
                          session_id=None,
                          force=False,
                          debug=False):  # Celery provides 'self'
    """Fetch detailed information for a specific session using VCONFDETAIL."""
    if not session_id:
        logger.error("session_id is required for fetch_session_details.")
        return

    logger.info(
        f"🔍 Fetching details for session: {session_id} (force={force}, debug={debug})"
    )
    if debug:
        logger.debug(
            f"🐛 DEBUG: Fetching details for session {session_id} in debug mode"
        )

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error("ASSEMBLY_API_KEY not configured.")
            return

        formatted_conf_id = format_conf_id(session_id)
        url = "https://open.assembly.go.kr/portal/openapi/VCONFDETAIL"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": formatted_conf_id
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if debug:
            logger.debug(
                f"🐛 DEBUG: VCONFDETAIL API response for {session_id}: {json.dumps(data, indent=2, ensure_ascii=False)}"
            )

        detail_data_item = None
        api_key_name = 'VCONFDETAIL'
        if data and api_key_name in data and isinstance(
                data[api_key_name], list):
            if len(data[api_key_name]) > 1 and isinstance(
                    data[api_key_name][1],
                    dict) and 'row' in data[api_key_name][1]:
                rows = data[api_key_name][1]['row']
                if rows and isinstance(rows, list) and len(rows) > 0:
                    detail_data_item = rows[0]
            elif len(data[api_key_name]) > 0 and isinstance(
                    data[api_key_name][0], dict):
                # Check head, similar to extract_sessions_from_response
                head_info = data[api_key_name][0].get('head')
                if head_info and head_info[0].get('RESULT', {}).get(
                        'CODE', '').startswith("INFO-200"):  # No data
                    logger.info(
                        f"API result for VCONFDETAIL ({session_id}) indicates no detailed data (INFO-200)."
                    )
                elif 'row' in data[api_key_name][
                        0]:  # Fallback for inconsistent structure
                    rows = data[api_key_name][0]['row']
                    if rows and isinstance(rows, list) and len(rows) > 0:
                        detail_data_item = rows[0]

        if not detail_data_item:
            logger.info(
                f"ℹ️ No detailed info available from VCONFDETAIL API for session {session_id}. Might be normal."
            )
            # Still proceed to fetch bills as they might be linked even without VCONFDETAIL entry
            if not debug:  # Avoid chaining calls rapidly in debug, or make it conditional
                if is_celery_available():
                    fetch_session_bills.delay(session_id=session_id,
                                              force=force,
                                              debug=debug)
                else:
                    fetch_session_bills(session_id=session_id,
                                        force=force,
                                        debug=debug)
            return

        if debug:
            logger.debug(
                f"🐛 DEBUG: Would update session {session_id} with details: {detail_data_item}"
            )
        else:
            try:
                session_obj = Session.objects.get(conf_id=session_id)
                updated_fields = False

                if detail_data_item.get('CONF_TIME'):
                    try:
                        time_str = detail_data_item.get('CONF_TIME', '09:00')
                        parsed_time = datetime.strptime(time_str,
                                                        '%H:%M').time()
                        if session_obj.bg_ptm != parsed_time:
                            session_obj.bg_ptm = parsed_time
                            updated_fields = True
                    except ValueError:
                        logger.warning(
                            f"Could not parse CONF_TIME: {detail_data_item.get('CONF_TIME')} for session {session_id}"
                        )

                if detail_data_item.get('ED_TIME'):
                    try:
                        time_str = detail_data_item.get('ED_TIME', '18:00')
                        parsed_time = datetime.strptime(time_str,
                                                        '%H:%M').time()
                        if session_obj.ed_ptm != parsed_time:
                            session_obj.ed_ptm = parsed_time
                            updated_fields = True
                    except ValueError:
                        logger.warning(
                            f"Could not parse ED_TIME: {detail_data_item.get('ED_TIME')} for session {session_id}"
                        )

                # Update other fields from VCONFDETAIL if they are more accurate or missing
                # e.g. 'CMITNM', 'CONFKINDNM' etc. if available and different from initial fetch
                if detail_data_item.get(
                        'TITLE') and session_obj.title != detail_data_item.get(
                            'TITLE'):
                    session_obj.title = detail_data_item.get('TITLE')
                    updated_fields = True

                if updated_fields or force:  # Save if fields changed or force is on
                    session_obj.save()
                    logger.info(
                        f"✅ Updated session details for: {session_id} from VCONFDETAIL."
                    )
                else:
                    logger.info(
                        f"No changes to session details for {session_id} from VCONFDETAIL or not in force mode."
                    )

                # Chain calls: fetch bills, then process PDF
                if is_celery_available():
                    fetch_session_bills.delay(session_id=session_id,
                                              force=force,
                                              debug=debug)
                else:
                    fetch_session_bills(session_id=session_id,
                                        force=force,
                                        debug=debug)

                if session_obj.down_url:  # PDF processing depends on down_url
                    if is_celery_available():
                        process_session_pdf.delay(session_id=session_id,
                                                  force=force,
                                                  debug=debug)
                    else:
                        process_session_pdf(session_id=session_id,
                                            force=force,
                                            debug=debug)
                else:
                    logger.info(
                        f"No PDF URL (down_url) for session {session_id}, skipping PDF processing."
                    )

            except Session.DoesNotExist:
                logger.error(
                    f"❌ Session {session_id} not found in database when trying to update details. Original session creation might have failed."
                )
            except Exception as e_db:
                logger.error(
                    f"❌ DB error updating session {session_id} details: {e_db}"
                )

    except RequestException as re_exc:
        logger.error(
            f"Request error fetching details for session {session_id}: {re_exc}"
        )
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for session details {session_id}.")
    except json.JSONDecodeError as json_e:
        logger.error(
            f"JSON decode error for session {session_id} details: {json_e}")
        # Probably don't retry JSON errors from API, it indicates bad data
    except Exception as e:
        logger.error(
            f"❌ Unexpected error fetching session {session_id} details: {e}")
        logger.exception(
            f"Full traceback for session {session_id} detail fetch:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected error for {session_id}.")
        # raise # Optionally


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
            for bill_item in bills_data_list:
                bill_id_api = bill_item.get('BILL_ID')
                if not bill_id_api:
                    logger.warning(
                        f"Skipping bill item due to missing BILL_ID in session {session_id}: {bill_item.get('BILL_NM', 'N/A')}"
                    )
                    continue

                bill_defaults = {
                    'session': session_obj,
                    'bill_nm': bill_item.get('BILL_NM', '제목 없는 의안').strip(),
                    'link_url': bill_item.get('LINK_URL', '')
                }

                # Add other fields like BILL_NO, PROPOSER, PROPOSE_DT if available from VCONFBILLLIST
                # and if your Bill model supports them.

                bill_obj, created = Bill.objects.update_or_create(
                    bill_id=
                    bill_id_api,  # BILL_ID from API is the primary key for bills
                    defaults=bill_defaults)

                if created:
                    created_count += 1
                    logger.info(
                        f"✨ Created new bill: {bill_id_api} ({bill_obj.bill_nm[:30]}...) for session {session_id}"
                    )
                else:  # Bill already existed, update_or_create updated it
                    updated_count += 1
                    logger.info(
                        f"🔄 Updated existing bill: {bill_id_api} ({bill_obj.bill_nm[:30]}...) for session {session_id}"
                    )
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


def get_all_assembly_members():
    """Get all assembly member names from local Speaker database."""
    try:
        # Get all speaker names from our local database
        speaker_names = set(Speaker.objects.values_list('naas_nm', flat=True))
        logger.info(f"✅ Using {len(speaker_names)} assembly member names from local database")
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
    """Extract and analyze statements for a specific bill text segment."""
    if not bill_text_segment: 
        return []

    logger.info(
        f"🔍 Processing bill segment: '{bill_name}' (session: {session_id}) - {len(bill_text_segment)} chars"
    )

    # Use batch processing for long text segments
    MAX_SEGMENT_LENGTH = 20000  # 20K characters
    if len(bill_text_segment) > MAX_SEGMENT_LENGTH:
        logger.info(
            f"Bill text segment too long ({len(bill_text_segment)} chars), processing in batches of {MAX_SEGMENT_LENGTH}"
        )
        # Process in batches
        batches = []
        for i in range(0, len(bill_text_segment), MAX_SEGMENT_LENGTH):
            batch = bill_text_segment[i:i + MAX_SEGMENT_LENGTH]
            batches.append(batch)

        logger.info(f"Processing {len(batches)} batches for bill '{bill_name}'")

        all_batch_statements = []
        for batch_idx, batch_text in enumerate(batches):
            logger.info(f"Processing batch {batch_idx + 1}/{len(batches)} for bill '{bill_name}'")
            batch_statements = process_single_segment_for_statements_with_splitting(
                batch_text, session_id, bill_name, debug)
            all_batch_statements.extend(batch_statements)
            if not debug:
                time.sleep(0.5)  # Brief pause between batches

        return all_batch_statements

    # Process single segment - use ◯ splitting approach
    return process_single_segment_for_statements_with_splitting(bill_text_segment, session_id, bill_name, debug)


def process_single_segment_for_statements_with_splitting(bill_text_segment,
                                                        session_id,
                                                        bill_name,
                                                        debug=False):
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
        if segment and len(segment) > 50:  # Only process segments with meaningful content
            speech_segments.append(segment)
    
    logger.info(
        f"Split text into {len(speech_segments)} individual speech segments based on ◯ markers. "
        f"Segment sizes: {[len(seg) for seg in speech_segments]} chars"
    )
    
    # Process segments with multithreading for LLM calls
    all_statements = process_speech_segments_multithreaded(
        speech_segments, session_id, bill_name, debug
    )
    
    logger.info(
        f"✅ ◯-based processing for '{bill_name}' resulted in {len(all_statements)} statements "
        f"from {len(speech_segments)} speech segments"
    )
    
    return all_statements


def process_speech_segments_multithreaded(speech_segments, session_id, bill_name, debug=False):
    """Process multiple speech segments with true parallel processing using batch analysis."""
    if not speech_segments:
        return []
    
    if debug:
        logger.debug(f"🐛 DEBUG: Would process {len(speech_segments)} segments in parallel batch")
        return []
    
    logger.info(f"🚀 Processing {len(speech_segments)} speech segments in parallel batch for bill '{bill_name}'")
    
    # Use the new batch processing function
    all_statements = analyze_speech_segment_with_llm_batch(
        speech_segments, session_id, bill_name, debug
    )
    
    logger.info(f"🎉 Parallel batch processing completed for '{bill_name}': {len(all_statements)} valid statements from {len(speech_segments)} segments")
    return all_statements


def process_single_segment_for_statements(bill_text_segment,
                                          session_id,
                                          bill_name,
                                          debug=False):
    """Fallback: Use splitting approach for single segments."""
    return process_single_segment_for_statements_with_splitting(
        bill_text_segment, session_id, bill_name, debug)


def analyze_speech_segment_with_llm_batch(speech_segments, session_id, bill_name, debug=False):
    """Batch analyze multiple speech segments with LLM without database operations."""
    if not model:
        logger.warning("❌ Main LLM ('model') not available. Cannot analyze speech segments.")
        return []

    if not speech_segments:
        return []

    logger.info(f"🚀 Batch analyzing {len(speech_segments)} speech segments for bill '{bill_name}'")
    
    # Get assembly members once for the entire batch
    assembly_members = get_all_assembly_members()
    
    # Process all segments in parallel using ThreadPoolExecutor
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all LLM tasks
        future_to_segment = {
            executor.submit(analyze_single_segment_llm_only, segment, bill_name, assembly_members): i 
            for i, segment in enumerate(speech_segments)
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_segment):
            segment_index = future_to_segment[future]
            try:
                result = future.result()
                if result:
                    result['segment_index'] = segment_index
                    results.append(result)
            except Exception as e:
                logger.error(f"❌ Exception in batch segment {segment_index}: {e}")
    
    logger.info(f"✅ Batch analysis completed: {len(results)} valid statements from {len(speech_segments)} segments")
    return sorted(results, key=lambda x: x.get('segment_index', 0))


def analyze_single_segment_llm_only(speech_segment, bill_name, assembly_members):
    """Analyze a single speech segment with LLM only - no database operations."""
    if not speech_segment or len(speech_segment) < 50:
        return None

    prompt = f"""
국회 회의록 발언 분석:
논의 중인 의안: "{bill_name}"
발언 세그먼트:
---
{speech_segment}
---

위 텍스트에서 발언자와 발언 내용을 분석하여 다음 JSON 형식으로 제공해주세요:
{{
  "speaker_name": "발언자 실명 (◯ 다음에 나오는 이름에서 직함 제거, 예: '김철수')",
  "speech_content": "발언자 이름 부분을 제거한 실제 발언 내용",
  "is_valid_member": true/false (실제 국회의원으로 판단되는지),
  "is_substantial": true/false (정책/의안 관련 실질적 발언인지),
  "sentiment_score": -1.0 부터 1.0 사이의 감성 점수,
  "sentiment_reason": "감성 판단 근거 (간략히)",
  "bill_relevance_score": 0.0 부터 1.0 사이의 의안 관련성 점수,
  "policy_categories": [
    {{
      "main_category": "주요 정책 분야 (경제, 복지, 교육, 외교안보, 환경, 법제, 과학기술, 문화, 농림, 국토교통, 행정, 기타)",
      "sub_category": "세부 정책 분야",
      "confidence": 0.0-1.0
    }}
  ],
  "key_policy_phrases": ["핵심 정책 관련 어구 최대 5개"],
  "bill_specific_keywords": ["'{bill_name}' 관련 직접 키워드 최대 3개"]
}}

기준:
1. speaker_name: ◯ 다음 이름에서 '의원', '위원장', '장관' 등 직함 제거
2. speech_content: 발언자 표시 부분 제거 후 실제 발언 내용만
3. is_valid_member: 실제 국회의원 이름인지 판단
4. is_substantial: 단순 인사/절차가 아닌 정책 논의인지
5. 의장, 위원장의 사회 발언은 is_substantial: false
6. bill_relevance_score: 명시된 의안과의 직접적 관련성
"""

    try:
        response = model.generate_content(prompt)
        if not response or not response.text:
            return None

        response_text_cleaned = response.text.strip().replace("```json", "").replace("```", "").strip()
        analysis_json = json.loads(response_text_cleaned)

        # Handle case where LLM returns a list instead of dict
        if isinstance(analysis_json, list):
            if len(analysis_json) > 0 and isinstance(analysis_json[0], dict):
                analysis_json = analysis_json[0]
            else:
                return None
        
        if not isinstance(analysis_json, dict):
            return None

        speaker_name = analysis_json.get('speaker_name', '').strip()
        speech_content = analysis_json.get('speech_content', '').strip()
        is_valid_member = analysis_json.get('is_valid_member', False)
        is_substantial = analysis_json.get('is_substantial', False)

        # Validate speaker name against assembly members
        is_real_member = False
        if speaker_name and assembly_members:
            name_for_matching = speaker_name
            for title in ['의원', '위원장', '장관', '의장', '부의장']:
                name_for_matching = name_for_matching.replace(title, '').strip()
            
            is_real_member = name_for_matching in assembly_members or speaker_name in assembly_members
            
            if not assembly_members:
                is_real_member = is_valid_member

        # Check if speaker should be ignored
        should_ignore = any(ignored in speaker_name for ignored in IGNORED_SPEAKERS) if speaker_name else True

        if not speaker_name or not speech_content or not is_valid_member or not is_substantial or should_ignore or not is_real_member:
            return None

        # Return the complete analysis
        return {
            'speaker_name': speaker_name,
            'text': speech_content,
            'sentiment_score': analysis_json.get('sentiment_score', 0.0),
            'sentiment_reason': analysis_json.get('sentiment_reason', 'LLM 분석 완료'),
            'bill_relevance_score': analysis_json.get('bill_relevance_score', 0.0),
            'policy_categories': analysis_json.get('policy_categories', []),
            'policy_keywords': analysis_json.get('key_policy_phrases', []),
            'bill_specific_keywords': analysis_json.get('bill_specific_keywords', [])
        }

    except Exception as e:
        logger.debug(f"Error analyzing segment: {e}")
        return None


def analyze_speech_segment_with_llm(speech_segment, session_id, bill_name, debug=False):
    """Legacy single segment analysis - kept for compatibility."""
    assembly_members = get_all_assembly_members()
    return analyze_single_segment_llm_only(speech_segment, bill_name, assembly_members)


def analyze_single_statement_with_bill_context(statement_data_dict,
                                               session_id,
                                               bill_name,
                                               debug=False):
    """Analyze a single statement's text using LLM, with context of a specific bill."""
    if not model:  # Global 'model' for detailed analysis (e.g., gemma-3)
        logger.warning(
            "❌ Main LLM ('model') not available. Cannot analyze statement for bill context."
        )
        # Return basic structure with indication of failure
        statement_data_dict.update({
            'sentiment_score': 0.0,
            'sentiment_reason': 'LLM N/A',
            'bill_relevance_score': 0.0,
            'policy_categories': [],
            'policy_keywords': [],
            'bill_specific_keywords': []
        })
        return statement_data_dict

    speaker_name = statement_data_dict.get('speaker_name', 'Unknown')
    text_to_analyze = statement_data_dict.get('text', '')

    if not text_to_analyze:
        logger.warning(
            f"No text to analyze for speaker '{speaker_name}' regarding bill '{bill_name}'."
        )
        return statement_data_dict

    # Use batch processing for very long statements
    MAX_STATEMENT_LENGTH = 8000  # 8k characters for individual statement analysis
    if len(text_to_analyze) > MAX_STATEMENT_LENGTH:
        logger.info(
            f"Statement text too long ({len(text_to_analyze)} chars), processing first {MAX_STATEMENT_LENGTH} chars"
        )
        text_for_prompt = text_to_analyze[:MAX_STATEMENT_LENGTH] + "... [발언이 길이 제한으로 잘렸습니다]"
    else:
        text_for_prompt = text_to_analyze

    prompt = f"""
국회 발언 분석 요청:
발언자: {speaker_name}
논의 중인 특정 의안: "{bill_name}"
발언 내용:
---
{text_for_prompt}
---

위 발언 내용을 분석하여 다음 JSON 형식으로 결과를 제공해주세요.
{{
  "sentiment_score": -1.0 (매우 부정적) 부터 1.0 (매우 긍정적) 사이의 감성 점수 (숫자),
  "sentiment_reason": "감성 판단의 주요 근거 (간략히, 1-2 문장)",
  "bill_relevance_score": 0.0 (의안과 무관) 부터 1.0 (의안과 매우 직접적 관련) 사이의 점수 (숫자). 이 발언이 구체적으로 "{bill_name}"에 대해 얼마나 논하고 있는지 판단해주세요.",
  "policy_categories": [
    {{
      "main_category": "주요 정책 분야 (경제, 복지, 교육, 외교안보, 환경, 법제, 과학기술, 문화, 농림, 국토교통, 행정, 기타 중 택1)",
      "sub_category": "세부 정책 분야 (예: '저출생 대응', '부동산 안정', 'AI 육성 등, 없으면 '일반')",
      "confidence": 0.0 부터 1.0 사이의 분류 확신도 (숫자)
    }}
  ],
  "key_policy_phrases": ["발언의 핵심 정책 관련 어구 (최대 5개 배열)"],
  "bill_specific_keywords_found": ["발언 내용 중 '{bill_name}' 또는 이와 관련된 직접적인 키워드가 있다면 배열로 제공 (최대 3개)"]
}}

분석 가이드라인:
1.  **Sentiment**: 발언자의 어조와 내용의 긍/부정성을 평가합니다. 중립은 0.0.
2.  **Bill Relevance**: 발언이 명시된 의안 "{bill_name}"과 얼마나 직접적으로 연관되어 있는지 평가합니다. 단순히 의안이 언급되는 회의에서의 발언이라고 높은 점수를 주지 마십시오. 내용 자체가 의안을 다루어야 합니다.
3.  **Policy Categories**: 발언의 주제를 가장 잘 나타내는 정책 분야를 선택합니다. 여러 분야에 걸칠 경우 가장 주요한 1~2개만 포함합니다. 다만 지역 관련의 경우, 그 지역의 명칭은 "서울", "제주" 와 같은 형식으로 분야의 개수를 제외하고 포함될 수 있습니다. confidence는 해당 분류에 대한 모델의 확신도입니다.
4.  **Key Policy Phrases**: 발언의 핵심 내용을 담고 있는 정책 관련 어구를 간결하게 추출합니다.
5.  **Bill Specific Keywords**: 발언 텍스트 내에서 "{bill_name}"의 전부 또는 일부, 혹은 이 의안의 핵심 내용을 지칭하는 특정 단어가 발견되면 기록합니다.

응답은 반드시 유효한 JSON 형식이어야 하며, 모든 문자열 값은 큰따옴표로 감싸야 합니다.
"""
    try:
        response = model.generate_content(
            prompt)  # Uses the global 'model' (e.g. gemma-3)
        if not response or not response.text:
            logger.warning(
                f"❌ No LLM analysis response for '{speaker_name}' on bill '{bill_name}'."
            )
            return statement_data_dict  # Return original dict

        response_text_cleaned = response.text.strip().replace(
            "```json", "").replace("```", "").strip()
        analysis_json = json.loads(response_text_cleaned)

        statement_data_dict.update({
            'sentiment_score':
            analysis_json.get('sentiment_score', 0.0),
            'sentiment_reason':
            analysis_json.get('sentiment_reason', 'LLM 분석 완료'),
            'bill_relevance_score':
            analysis_json.get('bill_relevance_score', 0.0),
            'policy_categories':
            analysis_json.get('policy_categories', []),
            'policy_keywords':
            analysis_json.get('key_policy_phrases',
                              []),  # Matched to prompt output key
            'bill_specific_keywords':
            analysis_json.get('bill_specific_keywords_found',
                              [])  # Matched to prompt output key
        })
        if debug:
            logger.debug(
                f"🐛 DEBUG: Analyzed '{speaker_name}' on '{bill_name}' - Sent: {statement_data_dict['sentiment_score']}, BillRel: {statement_data_dict['bill_relevance_score']}"
            )
        return statement_data_dict
    except json.JSONDecodeError as e:
        logger.error(
            f"❌ JSON parsing error for LLM analysis ('{speaker_name}' on '{bill_name}'): {e}. Response: {response_text_cleaned if 'response_text_cleaned' in locals() else 'N/A'}"
        )
    except Exception as e:
        logger.error(
            f"❌ Error during LLM analysis of statement for '{speaker_name}' on bill '{bill_name}': {e}"
        )
        logger.exception("Full traceback for statement analysis error:")
    # If error, return original dict to avoid breaking loop, but it won't have LLM data
    return statement_data_dict


def extract_statements_with_bill_based_chunking(full_text,
                                                session_id,
                                                bill_names_list,
                                                debug=False):
    """
    Process full text by first identifying bill segments using LLM,
    then processing each bill segment in chunks for statement extraction with multithreading.
    """
    logger.info(
        f"🔄 Using bill-based chunked processing for session: {session_id}")

    if not genai or not hasattr(genai, 'GenerativeModel'):
        logger.warning(
            "❌ Gemini API not configured. Cannot perform bill-based chunked processing."
        )
        return []

    try:
        segmentation_model_name = 'gemini-2.0-flash-lite'
        segmentation_llm = genai.GenerativeModel(segmentation_model_name)
        speaker_detection_llm = genai.GenerativeModel(segmentation_model_name)
    except Exception as e_model:
        logger.error(
            f"Failed to initialize models ({segmentation_model_name}): {e_model}"
        )
        return []

    all_analyzed_statements = []

    # Step 1: Get bill segments using LLM (use existing bill segmentation logic)
    bill_segments_from_llm = []
    if bill_names_list and len(bill_names_list) > 0:
        logger.info(
            f"🔍 Step 1: Identifying bill segments for session {session_id}")

        # Use batch processing for bill segmentation on very long texts
        MAX_SEGMENTATION_LENGTH = 100000
        if len(full_text) > MAX_SEGMENTATION_LENGTH:
            logger.info(
                f"Text too long for segmentation ({len(full_text)} chars), using first {MAX_SEGMENTATION_LENGTH} chars for bill identification"
            )
            segmentation_text = full_text[:MAX_SEGMENTATION_LENGTH] + "\n[텍스트가 길이 제한으로 잘렸습니다]"
        else:
            segmentation_text = full_text

        bill_segmentation_prompt = f"""
국회 회의록 전체 텍스트에서 논의된 주요 의안(법안)별로 구간을 나누어주세요.
다음은 이 회의에서 논의된 의안 목록입니다: {", ".join(bill_names_list)}

회의록 텍스트:
---
{segmentation_text}
---

각 의안에 대한 논의 시작 지점을 알려주세요. JSON 형식 응답:
{{
  "bill_discussion_segments": [
    {{
      "bill_name_identified": "LLM이 식별한 의안명 (목록에 있는 이름과 최대한 일치)",
      "discussion_start_idx": 해당 의안 논의가 시작되는 텍스트 내 문자 위치 (숫자),
      "relevance_to_provided_list": 0.0-1.0 (제공된 의안 목록과의 관련성 추정치)
    }}
  ]
}}

- "bill_name_identified"는 제공된 의안 목록에 있는 이름 중 하나와 일치하거나 매우 유사해야 합니다.
- "discussion_start_idx"는 회의록 텍스트 내에서의 정확한 문자 위치를 나타내야 합니다.
- 순서는 회의록에 나타난 순서대로 정렬해주세요.
"""

        try:
            seg_response = segmentation_llm.generate_content(
                bill_segmentation_prompt)
            if seg_response and seg_response.text:
                seg_text_cleaned = seg_response.text.strip().replace(
                    "```json", "").replace("```", "").strip()
                seg_data = json.loads(seg_text_cleaned)
                bill_segments_from_llm = seg_data.get(
                    "bill_discussion_segments", [])
                logger.info(
                    f"LLM identified {len(bill_segments_from_llm)} bill segments"
                )
        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                f"Error in bill segmentation: {e}. Will process as single bill segment."
            )
            # Fallback: treat entire text as one bill segment
            if bill_names_list:
                bill_segments_from_llm = [{
                    "bill_name_identified":
                    bill_names_list[0],
                    "discussion_start_idx":
                    0,
                    "relevance_to_provided_list":
                    0.5
                }]

    # Step 2: Create ordered bill segments with text
    sorted_segments_with_text = []
    if bill_segments_from_llm:
        valid_segments_for_sort = []
        for seg_info in bill_segments_from_llm:
            start_idx = seg_info.get("discussion_start_idx")
            if start_idx is not None and isinstance(
                    start_idx, int) and 0 <= start_idx < len(full_text):
                seg_info['start_index'] = start_idx
                valid_segments_for_sort.append(seg_info)

        # Sort by start_index
        valid_segments_for_sort.sort(key=lambda x: x['start_index'])

        # Define text segments
        for i, current_seg_info in enumerate(valid_segments_for_sort):
            segment_text_start_index = current_seg_info['start_index']
            segment_text_end_index = len(full_text)

            if i + 1 < len(valid_segments_for_sort):
                next_segment_start_index = valid_segments_for_sort[
                    i + 1]['start_index']
                segment_text_end_index = next_segment_start_index

            segment_actual_text = full_text[
                segment_text_start_index:segment_text_end_index]
            sorted_segments_with_text.append({
                "bill_name":
                current_seg_info.get("bill_name_identified",
                                     "Unknown Bill Segment"),
                "text":
                segment_actual_text
            })

    # If no segments identified, create one segment with first bill name or generic
    if not sorted_segments_with_text:
        bill_name_fallback = bill_names_list[
            0] if bill_names_list else "General Discussion"
        sorted_segments_with_text = [{
            "bill_name": bill_name_fallback,
            "text": full_text
        }]

    # Step 3: Process each bill segment in chunks with multithreading
    logger.info(
        f"🔍 Step 2: Processing {len(sorted_segments_with_text)} bill segments in chunks with multithreading"
    )

    for seg_data in sorted_segments_with_text:
        bill_name_for_seg = seg_data["bill_name"]
        bill_segment_text = seg_data["text"]

        logger.info(
            f"--- Processing bill segment: {bill_name_for_seg} ({len(bill_segment_text)} chars) ---"
        )

        # Process with multithreading regardless of size for consistent performance
        statements_in_segment = extract_statements_for_bill_segment(
            bill_segment_text, session_id, bill_name_for_seg, debug)
        for stmt_data in statements_in_segment:
            stmt_data['associated_bill_name'] = bill_name_for_seg
        all_analyzed_statements.extend(statements_in_segment)

    logger.info(
        f"✅ Bill-based chunked processing for session {session_id} completed: {len(all_analyzed_statements)} statements"
    )
    return all_analyzed_statements


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self,
                        session_id=None,
                        force=False,
                        debug=False):  # Celery provides 'self'
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
            f"ℹ️ No PDF URL (down_url) for session {session_id}. Skipping PDF processing."
        )
        return

    if Statement.objects.filter(
            session=session).exists() and not force and not debug:
        logger.info(
            f"Statements already exist for session {session_id} and not in force/debug mode. Skipping PDF reprocessing."
        )
        return

    if debug:
        logger.debug(
            f"🐛 DEBUG: Simulating PDF processing for {session_id}. NOT downloading or parsing in debug."
        )
        # Create one dummy statement for flow testing if needed in debug
        # get_or_create_speaker("테스트발언자", debug=True)
        # Statement.objects.get_or_create(session=session, speaker=Speaker.objects.first(), text="디버그용 테스트 발언입니다.", defaults={'sentiment_score':0.1})
        return

    temp_pdf_path = None  # Initialize
    try:
        logger.info(f"📥 Downloading PDF from: {session.down_url}")
        response = requests.get(
            session.down_url, timeout=120,
            stream=True)  # Increased timeout for large PDFs
        response.raise_for_status()

        temp_dir = Path(getattr(settings, "TEMP_FILE_DIR",
                                "temp_files"))  # Use configurable temp dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_pdf_path = temp_dir / f"session_{session_id}_{int(time.time())}.pdf"  # Add timestamp for uniqueness

        with open(temp_pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(
            f"📥 PDF for session {session_id} downloaded to {temp_pdf_path}")

        full_text = ""
        try:
            with pdfplumber.open(temp_pdf_path) as pdf:
                # PDF not being encrypted is ensured
                '''if pdf.is_encrypted:
                    logger.warning(
                        f"PDF {temp_pdf_path} is encrypted. Trying to extract text..."
                    )
                    # pdfplumber might need password if it's owner-password encrypted against text extraction'''

                pages = pdf.pages
                logger.info(
                    f"Extracting text from {len(pages)} pages in PDF for session {session_id}..."
                )
                for i, page in enumerate(pages):
                    page_text = page.extract_text(
                        x_tolerance=1, y_tolerance=3)  # Adjust tolerances
                    if page_text:
                        full_text += page_text + "\n"
                    if (i + 1) % 20 == 0:
                        logger.info(f"Processed {i+1}/{len(pages)} pages...")
            logger.info(
                f"📄 Extracted ~{len(full_text)} chars from PDF for session {session_id}."
            )
        except Exception as e_parse:  # Catch pdfplumber specific errors
            logger.error(
                f"❌ Error extracting text using pdfplumber for {session_id} from {temp_pdf_path}: {e_parse}"
            )
            if "Incorrect থানা opening times password" in str(
                    e_parse):  # Specific error for some password types
                logger.error(
                    "PDF might be password protected against text extraction.")
            return  # Stop if text extraction fails

        if not full_text.strip():
            logger.warning(
                f"Extracted text is empty for session {session_id}. PDF might be image-based or have extraction issues."
            )
            return

        # Fetch bill context (names of bills discussed in this session) for LLM
        bills_for_session = get_session_bill_names(
            session_id)  # Uses DB Bill objects
        bills_context_str = ", ".join(
            bills_for_session) if bills_for_session else "여러 의안"
        logger.info(
            f"Bills context for session {session_id} LLM: {bills_context_str[:200]}..."
        )

        # Core logic: Process the extracted text to get statements
        # This will use the multi-stage LLM approach (bill segmentation, then speaker/content)
        process_pdf_text_for_statements(full_text, session_id, session,
                                        bills_context_str, bills_for_session,
                                        debug)

    except RequestException as re_exc:
        logger.error(
            f"Request error downloading PDF for session {session_id}: {re_exc}"
        )
        try:
            self.retry(exc=re_exc)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for PDF download {session_id}.")
    except Exception as e:
        logger.error(
            f"❌ Unexpected error processing PDF for session {session_id}: {e}")
        logger.exception(f"Full traceback for PDF processing {session_id}:")
        try:
            self.retry(exc=e)  # Retry for other unexpected errors too
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries after unexpected PDF error {session_id}.")
        # raise # Optionally
    finally:
        if temp_pdf_path and temp_pdf_path.exists():
            try:
                temp_pdf_path.unlink()
                logger.info(f"🗑️ Deleted temporary PDF: {temp_pdf_path}")
            except OSError as e_del:
                logger.error(
                    f"Error deleting temporary PDF {temp_pdf_path}: {e_del}")


@shared_task(bind=True, max_retries=1,
             default_retry_delay=300)  # Less retries for costly LLM task
def analyze_statement_categories(self,
                                 statement_id=None):  # Celery provides 'self'
    """Analyze categories and sentiment for an existing statement using LLM. (Usually part of initial processing)"""
    if not statement_id:
        logger.error(
            "statement_id is required for analyze_statement_categories.")
        return

    if not model:  # Global 'model'
        logger.warning(
            "❌ Main LLM ('model') not available. Cannot analyze statement categories."
        )
        return

    try:
        statement = Statement.objects.get(id=statement_id)
        # Potentially skip if already analyzed to a satisfactory degree, unless forced
        if statement.sentiment_score is not None and statement.category_analysis and not getattr(
                self, 'force_reanalyze', False):
            logger.info(
                f"Statement {statement_id} already analyzed. Skipping re-analysis."
            )
            return

    except Statement.DoesNotExist:
        logger.error(
            f"Statement with id {statement_id} not found for analysis.")
        return

    logger.info(
        f"Analyzing categories for statement ID: {statement_id} by {statement.speaker.naas_nm}"
    )
    text_to_analyze = statement.text
    text_for_prompt = text_to_analyze

    # Generic analysis prompt (not bill-specific, as bill context might not be available here)
    # This function is more for re-analysis or if initial processing missed it.
    # The `analyze_single_statement_with_bill_context` is preferred during initial PDF processing.
    prompt = f"""
국회 발언 분석 요청:
발언자: {statement.speaker.naas_nm}
발언 내용:
---
{text_for_prompt}
---

위 발언 내용을 분석하여 다음 JSON 형식으로 결과를 제공해주세요.
{{
  "sentiment_score": -1.0 부터 1.0 사이의 감성 점수 (숫자),
  "sentiment_reason": "감성 판단의 주요 근거 (간략히)",
  "policy_categories": [
    {{
      "main_category": "주요 정책 분야 (경제, 복지, 교육, 외교안보, 환경, 법제, 과학기술, 문화, 농림, 국토교통, 행정, 기타 중 택1)",
      "sub_category": "세부 정책 분야 (없으면 '일반')",
      "confidence": 0.0 부터 1.0 사이의 분류 확신도 (숫자)
    }}
  ],
  "key_policy_phrases": ["발언의 핵심 정책 관련 어구 (최대 5개 배열)"]
}}
(가이드라인은 analyze_single_statement_with_bill_context 와 유사하게 적용)
응답은 반드시 유효한 JSON 형식이어야 합니다.
"""

    try:
        response = model.generate_content(prompt)
        if not response or not response.text:
            logger.warning(
                f"❌ No LLM response for category analysis of statement {statement_id}"
            )
            return

        response_text_cleaned = response.text.strip().replace(
            "```json", "").replace("```", "").strip()
        analysis_json = json.loads(response_text_cleaned)

        statement.sentiment_score = analysis_json.get(
            'sentiment_score',
            statement.sentiment_score)  # Keep old if new is missing
        statement.sentiment_reason = analysis_json.get(
            'sentiment_reason', statement.sentiment_reason)
        statement.policy_keywords = ', '.join(
            analysis_json.get('key_policy_phrases', []))

        policy_categories_json = analysis_json.get('policy_categories', [])
        statement.category_analysis = json.dumps(
            policy_categories_json, ensure_ascii=False
        ) if policy_categories_json else statement.category_analysis

        statement.save()

        # Update/Create category associations in StatementCategory model
        if policy_categories_json:
            create_statement_categories(statement, policy_categories_json)

        logger.info(
            f"✅ LLM Category analysis completed for statement {statement_id}.")

    except json.JSONDecodeError as e:
        logger.error(
            f"❌ JSON parsing error for LLM category analysis (statement {statement_id}): {e}. Response: {response_text_cleaned if 'response_text_cleaned' in locals() else 'N/A'}"
        )
    except Exception as e:
        logger.error(
            f"❌ Error analyzing categories for statement {statement_id}: {e}")
        logger.exception("Full traceback for category analysis error:")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"Max retries for category analysis {statement_id}.")
        # raise # Optionally


def split_text_into_chunks(text, max_chunk_size):
    """Split text into chunks, trying to break at speaker markers (◯) when possible."""
    if len(text) <= max_chunk_size:
        return [text]

    chunks = []
    current_pos = 0

    while current_pos < len(text):
        # Define the end position for this chunk
        chunk_end = min(current_pos + max_chunk_size, len(text))

        # If we're not at the end of the text, try to find a good break point
        if chunk_end < len(text):
            # Look for speaker markers (◯) within the last 2000 characters of the chunk
            search_start = max(current_pos, chunk_end - 2000)
            last_speaker_pos = text.rfind('◯', search_start, chunk_end)

            if last_speaker_pos != -1 and last_speaker_pos > current_pos:
                # Found a speaker marker, break there
                chunk_end = last_speaker_pos
            else:
                # No speaker marker found, try to break at a line break
                last_newline = text.rfind('\n', search_start, chunk_end)
                if last_newline != -1 and last_newline > current_pos:
                    chunk_end = last_newline

        chunk = text[current_pos:chunk_end]
        if chunk.strip():  # Only add non-empty chunks
            chunks.append(chunk)

        current_pos = chunk_end

        # Skip any whitespace at the beginning of the next chunk
        while current_pos < len(text) and text[current_pos].isspace():
            current_pos += 1

    return chunks


def clean_pdf_text(text):
    """Clean PDF text by removing session identifiers and normalizing line breaks."""
    import re

    if not text:
        return text

    # Remove session identifier patterns like "제424회-제6차(2025년4월24일)"
    session_pattern = r'^제\d+회-제\d+차\(\d{4}년\d{1,2}월\d{1,2}일\)$'
    lines = text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if line and not re.match(session_pattern, line):
            # Replace all \n with spaces within the line content
            line = line.replace('\n', ' ')
            # Normalize multiple spaces to single space
            line = re.sub(r'\s+', ' ', line).strip()
            if line:  # Only add non-empty lines
                cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def process_pdf_text_for_statements(full_text,
                                    session_id,
                                    session_obj,
                                    bills_context_str,
                                    bill_names_list,
                                    debug=False):
    """
    Main orchestrator for processing full PDF text.
    Uses multi-stage LLM:
    1. Bill Segmentation (optional, can fallback)
    2. Speaker/Content Extraction per segment (or for full text if no segments)
    3. Detailed Analysis per extracted statement.
    """
    if not model or not genai:  # Check for main model and genai module
        logger.warning(
            "❌ LLM not available. Skipping statement extraction from PDF text."
        )
        # Optionally, could call a very basic regex fallback here if desired as a last resort
        # statements_data_fallback = extract_statements_with_regex_fallback(full_text, session_id, debug)
        # process_extracted_statements_data(statements_data_fallback, session_obj, debug, associated_bill_name="Regex Fallback")
        return

    # Clean the full text before processing
    logger.info(f"🧹 Cleaning PDF text for session {session_id}")
    full_text = clean_pdf_text(full_text)
    logger.info(f"📄 Cleaned text length: ~{len(full_text)} chars")

    logger.info(
        f"🤖 Starting LLM-based statement processing for session PDF {session_id}."
    )

    all_extracted_statements_data = [
    ]  # List of dicts, each a statement with analysis

    # Stage 0: Bill Segmentation (optional, but preferred if bills_names_list is rich)
    # Using a lighter model for segmentation.
    try:
        segmentation_model_name = 'gemini-2.0-flash-lite'
        segmentation_llm = genai.GenerativeModel(segmentation_model_name)
    except Exception as e_model:
        logger.error(
            f"Failed to initialize segmentation model ({segmentation_model_name}): {e_model}. Will process full text."
        )
        segmentation_llm = None

    bill_segments_from_llm = []
    if segmentation_llm and bill_names_list and len(
            bill_names_list) > 1:  # Only segment if multiple bills context
        logger.info(
            f"🔍 Stage 0 (Bill Segment): Attempting to segment transcript by bills for session {session_id}"
        )

        # Limit text for segmentation to prevent prompt overflow
        MAX_SEGMENTATION_LENGTH = 100000  # 100k characters for segmentation
        segmentation_text = full_text
        if len(full_text) > MAX_SEGMENTATION_LENGTH:
            logger.warning(
                f"Text too long for segmentation ({len(full_text)} chars), truncating to {MAX_SEGMENTATION_LENGTH}"
            )
            segmentation_text = full_text[:MAX_SEGMENTATION_LENGTH] + "\n[텍스트가 길이 제한으로 잘렸습니다]"

        bill_segmentation_prompt = f"""
국회 회의록 전체 텍스트에서 논의된 주요 의안(법안)별로 구간을 나누어주세요.
다음은 이 회의에서 논의된 의안 목록입니다: {", ".join(bill_names_list)}

회의록 텍스트:
---
{segmentation_text}
---

각 의안에 대한 논의 시작 지점을 알려주세요. JSON 형식 응답:
{{
  "bill_discussion_segments": [
    {{
      "bill_name_identified": "LLM이 식별한 의안명 (목록에 있는 이름과 최대한 일치)",
      "discussion_start_idx": 해당 의안 논의가 시작되는 텍스트 내 문자 위치 (숫자),
      "relevance_to_provided_list": 0.0-1.0 (제공된 의안 목록과의 관련성 추정치)
    }}
  ],
  "general_discussion_idx": 특정 의안에 해당하지 않는 일반 토론 시작 지점의 문자 위치 (숫자, 있을 경우)
}}

- "bill_name_identified"는 제공된 의안 목록에 있는 이름 중 하나와 일치하거나 매우 유사해야 합니다.
- "discussion_start_idx"는 회의록 텍스트 내에서의 정확한 문자 위치를 나타내야 합니다.
- 순서는 회의록에 나타난 순서대로 정렬해주세요.
"""
        try:
            seg_response = segmentation_llm.generate_content(
                bill_segmentation_prompt)
            if seg_response and seg_response.text:
                seg_text_cleaned = seg_response.text.strip().replace(
                    "```json", "").replace("```", "").strip()
                seg_data = json.loads(seg_text_cleaned)
                bill_segments_from_llm = seg_data.get(
                    "bill_discussion_segments", [])
                # general_cue = seg_data.get("general_discussion_cue") # Can handle this later
                if bill_segments_from_llm:
                    logger.info(
                        f"LLM identified {len(bill_segments_from_llm)} potential bill discussion segments."
                    )
                else:
                    logger.info(
                        "LLM did not identify distinct bill segments. Will process full text."
                    )
            else:
                logger.info(
                    "No response from LLM for bill segmentation. Will process full text."
                )
        except json.JSONDecodeError as e_json_seg:
            logger.error(
                f"JSON parsing error for bill segmentation response: {e_json_seg}. Processing full text."
            )
        except Exception as e_seg:
            logger.error(
                f"Error during LLM bill segmentation: {e_seg}. Processing full text."
            )
            logger.exception("Traceback for bill segmentation error:")

    # Sort segments by their appearance order in the full_text using their indices
    sorted_segments_with_text = []
    if bill_segments_from_llm:
        valid_segments_for_sort = []
        for seg_info in bill_segments_from_llm:
            start_idx = seg_info.get("discussion_start_idx")
            if start_idx is not None and isinstance(
                    start_idx, int) and 0 <= start_idx < len(full_text):
                seg_info['start_index'] = start_idx
                valid_segments_for_sort.append(seg_info)

        # Sort by start_index
        valid_segments_for_sort.sort(key=lambda x: x['start_index'])

        # Now define the actual text for each segment
        for i, current_seg_info in enumerate(valid_segments_for_sort):
            segment_text_start_index = current_seg_info['start_index']
            segment_text_end_index = len(full_text)  # Default to end

            if i + 1 < len(
                    valid_segments_for_sort):  # If there's a next segment
                next_segment_start_index = valid_segments_for_sort[
                    i + 1]['start_index']
                segment_text_end_index = next_segment_start_index

            segment_actual_text = full_text[
                segment_text_start_index:segment_text_end_index]
            sorted_segments_with_text.append({
                "bill_name":
                current_seg_info.get("bill_name_identified",
                                     "Unknown Bill Segment"),
                "text":
                segment_actual_text
            })
        logger.info(
            f"Successfully ordered {len(sorted_segments_with_text)} bill segments by appearance."
        )

    if sorted_segments_with_text:
        logger.info(
            f"Processing {len(sorted_segments_with_text)} identified bill text segments..."
        )
        for seg_data in sorted_segments_with_text:
            bill_name_for_seg = seg_data["bill_name"]
            text_of_segment = seg_data["text"]
            logger.info(
                f"--- Processing segment for Bill: {bill_name_for_seg} ({len(text_of_segment)} chars) ---"
            )

            # This function returns a list of DICTS, where each dict has speaker, text, and LLM analysis fields
            statements_in_segment = extract_statements_for_bill_segment(
                text_of_segment, session_id, bill_name_for_seg, debug)
            for stmt_data in statements_in_segment:
                stmt_data[
                    'associated_bill_name'] = bill_name_for_seg  # Add association
            all_extracted_statements_data.extend(statements_in_segment)
            if not debug:
                time.sleep(1)  # Pause between processing major segments
    else:
        logger.info(
            "No bill segments identified or bill-based processing failed. Using bill-based chunking approach."
        )
        # This function returns list of DICTS (speaker, text, LLM analysis fields)
        all_extracted_statements_data = extract_statements_with_bill_based_chunking(
            full_text, session_id, bill_names_list, debug)

    # Final step: Save all collected and analyzed statements to DB
    logger.info(
        f"Collected a total of {len(all_extracted_statements_data)} analyzed statements for session {session_id}."
    )
    if not debug and all_extracted_statements_data:
        process_extracted_statements_data(all_extracted_statements_data,
                                          session_obj, debug)
    elif debug and all_extracted_statements_data:
        logger.debug(
            f"🐛 DEBUG: Would save {len(all_extracted_statements_data)} statements. First one: {all_extracted_statements_data[0] if all_extracted_statements_data else 'None'}"
        )


def process_extracted_statements_data(statements_data_list,
                                      session_obj,
                                      debug=False):
    """Saves a list of processed statement data (dictionaries) to the database."""
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

    created_count = 0
    logger.info(
        f"Attempting to save {len(statements_data_list)} statements for session {session_obj.conf_id}."
    )
    for stmt_data in statements_data_list:
        try:
            speaker_name = stmt_data.get('speaker_name', '').strip()
            statement_text = stmt_data.get('text', '').strip()

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
                    "Unknown Bill Segment"
            ]:
                # Try to find the Bill object precisely
                try:
                    associated_bill_obj = _find_bill_for_statement(
                        session_obj, assoc_bill_name_from_data)
                    if not associated_bill_obj and Bill.objects.filter(
                            session=session_obj,
                            bill_nm__icontains=assoc_bill_name_from_data.split(
                                '(')[0].strip()).count() > 1:
                        logger.warning(
                            f"Ambiguous bill name '{assoc_bill_name_from_data}' for session {session_obj.conf_id}, found multiple matches. Not associating."
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
                category_analysis=json.dumps(stmt_data.get(
                    'policy_categories', []),
                                             ensure_ascii=False),
                policy_keywords=', '.join(stmt_data.get('policy_keywords',
                                                        [])),
                # Add new fields if your model has them
                bill_relevance_score=stmt_data.get(
                    'bill_relevance_score'),  # May be None
                bill_specific_keywords_json=json.dumps(stmt_data.get(
                    'bill_specific_keywords', []),
                                                       ensure_ascii=False))
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
        f"🎉 Saved {created_count} new statements for session {session_obj.conf_id}."
    )





def extract_statements_with_regex_fallback(text, session_id, debug=False):
    """
    Very basic regex fallback. Highly unreliable for complex transcripts.
    Primarily for contingency if LLMs are completely down.
    This does NOT perform any semantic analysis, just pattern matching.
    """
    import re
    logger.warning(
        f"⚠️ Using basic regex fallback for statement extraction (session: {session_id}). Results will be very rough."
    )

    cleaned_text = re.sub(r'\n+', '\n', text).replace('\r',
                                                      '')  # Normalize newlines

    # Regex attempts to find "◯ Speaker Name potentially with (title) some speech content"
    # until the next "◯ Speaker" or end of text. This is very greedy and simple.
    # Pattern: ◯ (Anything not ◯ or newline: speaker part) (newline or space) (Anything until next ◯ or end of text)
    # This is extremely basic and prone to errors.
    # A more robust regex would need careful crafting and testing on transcript data.
    # Example: ◯(?P<speaker>[^◯\n]+?)(?:의원|위원장|장관| 차관| 실장| 대변인)?\s*(?P<content>.+?)(?=◯|$)

    # Simpler version: find lines starting with ◯, assume name is up to first space or (
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


def analyze_single_statement(statement_data_dict, session_id, debug=False):
    """
    Analyzes a single statement's text using LLM (generic, no specific bill context passed to LLM).
    This is used when a statement is not tied to a pre-identified bill segment.
    Input: statement_data_dict = {'speaker_name': '...', 'text': '...'}
    Output: Updated statement_data_dict with LLM analysis fields.
    """
    if not model:  # Global 'model'
        logger.warning(
            "❌ Main LLM ('model') not available. Cannot analyze statement (generic)."
        )
        statement_data_dict.update({
            'sentiment_score': 0.0,
            'sentiment_reason': 'LLM N/A',
            'policy_categories': [],
            'policy_keywords': []
        })
        return statement_data_dict

    speaker_name = statement_data_dict.get('speaker_name', 'Unknown')
    text_to_analyze = statement_data_dict.get('text', '')

    if not text_to_analyze:
        logger.warning(
            f"No text to analyze for speaker '{speaker_name}' (generic analysis)."
        )
        return statement_data_dict

    text_for_prompt = text_to_analyze

    # This prompt is similar to analyze_single_statement_with_bill_context but WITHOUT explicit bill_name or bill_relevance.
    prompt = f"""
국회 발언 분석 요청:
발언자: {speaker_name}
발언 내용:
---
{text_for_prompt}
---

위 발언 내용을 분석하여 다음 JSON 형식으로 결과를 제공해주세요.
{{
  "sentiment_score": -1.0 부터 1.0 사이의 감성 점수 (숫자),
  "sentiment_reason": "감성 판단의 주요 근거 (간략히)",
  "policy_categories": [
    {{
      "main_category": "주요 정책 분야 (경제, 복지, 교육, 외교안보, 환경, 법제, 과학기술, 문화, 농림, 국토교통, 행정, 기타 중 택1)",
      "sub_category": "세부 정책 분야 (없으면 '일반')",
      "confidence": 0.0 부터 1.0 사이의 분류 확신도 (숫자)
    }}
  ],
  "key_policy_phrases": ["발언의 핵심 정책 관련 어구 (최대 5개 배열)"]
}}
(가이드라인은 이전 분석 함수들과 유사하게 적용)
응답은 반드시 유효한 JSON 형식이어야 합니다.
"""
    try:
        response = model.generate_content(prompt)
        if not response or not response.text:
            logger.warning(
                f"❌ No LLM generic analysis response for '{speaker_name}'.")
            return statement_data_dict

        response_text_cleaned = response.text.strip().replace(
            "```json", "").replace("```", "").strip()
        analysis_json = json.loads(response_text_cleaned)

        statement_data_dict.update({
            'sentiment_score':
            analysis_json.get('sentiment_score', 0.0),
            'sentiment_reason':
            analysis_json.get('sentiment_reason', 'LLM 분석 완료'),
            'policy_categories':
            analysis_json.get('policy_categories', []),
            'policy_keywords':
            analysis_json.get('key_policy_phrases', [])
            # No bill_relevance_score or bill_specific_keywords here
        })
        if debug:
            logger.debug(
                f"🐛 DEBUG: Generic analysis for '{speaker_name}' - Sentiment: {statement_data_dict['sentiment_score']}"
            )
        return statement_data_dict
    except json.JSONDecodeError as e:
        logger.error(
            f"❌ JSON parsing error for LLM generic analysis ('{speaker_name}'): {e}. Response: {response_text_cleaned if 'response_text_cleaned' in locals() else 'N/A'}"
        )
    except Exception as e:
        logger.error(
            f"❌ Error during LLM generic analysis of statement for '{speaker_name}': {e}"
        )
    return statement_data_dict


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
    """Create/update Category, Subcategory, and StatementCategory associations for a Statement."""
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
    """
    Get or create speaker. Relies on `fetch_speaker_details` for new speakers.
    LLM should provide a cleaned name, but this function can handle some variation.
    """
    if not speaker_name_raw or not speaker_name_raw.strip():
        logger.warning(
            "Empty speaker_name_raw provided to get_or_create_speaker.")
        return None

    speaker_name_cleaned = speaker_name_raw.strip()

    if not speaker_name_cleaned:  # If stripping resulted in empty name
        logger.warning(
            f"Speaker name '{speaker_name_raw}' became empty after cleaning.")
        return None

    @with_db_retry
    def _get_or_create_speaker_db():
        # Try to find by exact cleaned name first
        speaker_obj = Speaker.objects.filter(
            naas_nm=speaker_name_cleaned).first()

        if speaker_obj:
            if debug:
                logger.debug(f"Found existing speaker: {speaker_name_cleaned}")
            return speaker_obj

        # If still not found, this speaker is new to our DB.
        # Attempt to fetch full details from API.
        logger.info(
            f"Speaker '{speaker_name_cleaned}' not found in DB. Attempting to fetch details from API."
        )

        # `fetch_speaker_details` tries to get/create from API and returns the Speaker object.
        if not debug:  # Avoid external API calls in some debug scenarios for speed/cost
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

        # Fallback: Create a temporary/basic speaker record if API fetch fails or in debug
        # Use a unique naas_cd for these temporary entries.
        temp_naas_cd = f"TEMP_{speaker_name_cleaned.replace(' ', '_')}_{int(time.time())}"

        speaker_obj, created = Speaker.objects.get_or_create(
            naas_nm=speaker_name_cleaned,  # Try to create with the cleaned name
            defaults=
            {  # Provide all required non-nullable fields with placeholders
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
        if created:
            logger.info(
                f"Created basic/temporary speaker record for: {speaker_name_cleaned} (ID: {speaker_obj.naas_cd}). Details might be incomplete."
            )
        else:  # Should not happen if previous checks were exhaustive, but good fallback
            logger.info(
                f"Found speaker {speaker_name_cleaned} via get_or_create after API attempt."
            )
        return speaker_obj

    try:
        return _get_or_create_speaker_db()
    except Exception as e:
        logger.error(
            f"❌ Error in get_or_create_speaker for '{speaker_name_raw}' after retries: {e}"
        )
        logger.exception("Full traceback for get_or_create_speaker error:")
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def fetch_additional_data_nepjpxkkabqiqpbvk(self,
                                            force=False,
                                            debug=False
                                            ):  # Celery provides 'self'
    """Fetch additional data using nepjpxkkabqiqpbvk API endpoint."""
    api_endpoint_name = "nepjpxkkabqiqpbvk"  # Store endpoint name for logging
    logger.info(
        f"🔍 Fetching additional data from {api_endpoint_name} API (force={force}, debug={debug})"
    )

    if debug:
        logger.debug(
            f"🐛 DEBUG: Skipping actual API call for {api_endpoint_name} in debug mode."
        )
        return

    try:
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            logger.error(
                f"ASSEMBLY_API_KEY not configured for {api_endpoint_name}.")
            return

        url = f"https://open.assembly.go.kr/portal/openapi/{api_endpoint_name}"

        # Paginate through results if necessary
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
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()

            # Generic API response parsing, adapt to specific structure of 'nepjpxkkabqiqpbvk'
            items_on_page = []
            if data and api_endpoint_name in data and isinstance(
                    data[api_endpoint_name], list):
                if len(data[api_endpoint_name]) > 1 and isinstance(
                        data[api_endpoint_name][1], dict):
                    items_on_page = data[api_endpoint_name][1].get('row', [])
                elif len(data[api_endpoint_name]) > 0 and isinstance(
                        data[api_endpoint_name][0], dict):
                    head_info = data[api_endpoint_name][0].get('head')
                    if head_info and head_info[0].get('RESULT', {}).get(
                            'CODE', '').startswith("INFO-200"):  # No more data
                        logger.info(
                            f"API result for {api_endpoint_name} (page {current_page}) indicates no more data."
                        )
                        break  # End pagination
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
        # raise # Optionally


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_voting_data_for_bill(self, bill_id, force=False, debug=False):
    """Fetch voting data for a specific bill using nojepdqqaweusdfbi API."""
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

        created_count = 0
        updated_count = 0

        for vote_item in voting_data:
            try:
                member_name = vote_item.get('HG_NM', '').strip()
                vote_result = vote_item.get('RESULT_VOTE_MOD', '').strip()
                vote_date_str = vote_item.get('VOTE_DATE', '')

                if not member_name or not vote_result:
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

                # Find the speaker by name
                speaker = None
                speakers = Speaker.objects.filter(
                    naas_nm__icontains=member_name)
                if speakers.count() == 1:
                    speaker = speakers.first()
                elif speakers.count() > 1:
                    # Try exact match first
                    exact_match = speakers.filter(naas_nm=member_name).first()
                    if exact_match:
                        speaker = exact_match
                    else:
                        speaker = speakers.first()
                        logger.warning(
                            f"Multiple speakers found for {member_name}, using first match"
                        )

                if not speaker:
                    logger.warning(
                        f"Speaker not found for voting record: {member_name}")
                    continue

                # Create or update voting record
                voting_record, created = VotingRecord.objects.update_or_create(
                    bill=bill,
                    speaker=speaker,
                    defaults={
                        'vote_result': vote_result,
                        'vote_date': vote_date,
                        'session': bill.session
                    })

                if created:
                    created_count += 1
                    logger.info(
                        f"✨ Created voting record: {member_name} - {vote_result} for {bill.bill_nm[:30]}..."
                    )
                else:
                    updated_count += 1
                    logger.info(
                        f"🔄 Updated voting record: {member_name} - {vote_result} for {bill.bill_nm[:30]}..."
                    )

            except Exception as e_vote:
                logger.error(
                    f"❌ Error processing vote item for {bill_id}: {e_vote}. Item: {vote_item}"
                )
                continue

        logger.info(
            f"🎉 Voting data processed for bill {bill_id}: {created_count} created, {updated_count} updated."
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