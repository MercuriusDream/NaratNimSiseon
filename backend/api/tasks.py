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

logger = logging.getLogger(__name__)

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

            session_obj, created = Session.objects.update_or_create(
                conf_id=confer_num, defaults=session_defaults)

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


def extract_statements_for_bill_segment(bill_text_segment,
                                        session_id,
                                        bill_name,
                                        debug=False):
    """Extract and analyze statements for a specific bill text segment using LLM."""
    if not bill_text_segment: return []

    logger.info(
        f"🔍 Stage 1 (Speaker Detect): For bill '{bill_name}' (session: {session_id})"
    )

    if not genai or not hasattr(genai, 'GenerativeModel'):
        logger.warning(
            "❌ Gemini API not configured. Cannot perform speaker detection for bill segment."
        )
        return []

    try:
        # Use a lighter/cheaper model for speaker detection stage if appropriate
        speaker_detection_model_name = 'gemini-2.0-flash-lite'  # Or 'gemini-2.0-flash-lite' if still available & preferred
        speaker_detection_llm = genai.GenerativeModel(
            speaker_detection_model_name)
    except Exception as e_model:
        logger.error(
            f"Failed to initialize speaker detection model ({speaker_detection_model_name}): {e_model}"
        )
        return []

    # Limit text length for prompts, Not needed for now
    '''
    prompt_text_limit = 7500 # Characters, adjust based on model context window and typical segment size
    if len(bill_text_segment) > prompt_text_limit:
        logger.warning(f"Bill text for '{bill_name}' truncated from {len(bill_text_segment)} to {prompt_text_limit} chars for speaker detection prompt.")
        bill_text_segment_for_prompt = bill_text_segment[:prompt_text_limit]
    else:
        bill_text_segment_for_prompt = bill_text_segment
    '''

    speaker_detection_prompt = f"""
다음은 국회 회의록의 일부이며, "{bill_name}" 의안과 관련된 부분으로 추정됩니다.
이 구간에서 국회의원들의 개별 발언을 정확히 식별하고, 발언자와 발언 시작/종료 지점을 알려주세요.

논의 중인 의안: {bill_name}

회의록 텍스트 일부:
---
{bill_text_segment}
---

각 발언에 대해 다음 정보를 JSON 형식으로 제공해주세요. 배열 'detected_speeches' 안에 객체로 포함합니다:
{{
  "speaker_name_raw": "회의록에 기록된 발언자 이름 원본 (예: 김철수의원)",
  "speaker_name_clean": "정리된 발언자 실명 (예: 김철수)",
  "speech_start_cue": "해당 발언이 시작되는 고유한 짧은 텍스트 조각 (회의록 원문에서 약 15-20자, 예: '◯김철수의원 уважаемые...')",
  "is_real_person_guess": true/false (실제 국회의원 이름으로 판단되는지 여부),
  "is_substantial_discussion_guess": true/false (단순 절차 안내가 아닌, 실질적인 정책/의안 논의인지 여부)
}}

기준:
1. '◯' (동그라미) 기호로 시작하고 사람 이름으로 보이는 부분만 발언으로 간주합니다.
2. '의장', '위원장' 등이 사회를 보는 발언은 is_substantial_discussion_guess: false로 처리합니다. 단, 위원장이 개인 의견을 표명하는 경우는 true일 수 있습니다.
3. 법률명, 기관명, 직책명만 있는 경우는 발언자로 보지 않습니다.
4. "존경하는", "감사합니다" 등 단순 인사나 절차적 발언(예: "이의 없으십니까?")은 is_substantial_discussion_guess: false 입니다.
5. speaker_name_clean은 '의원', '장관', '위원장' 등 직함을 제외하고 이름만 추출합니다 (예: "김XX 의원" -> "김XX").

응답은 다음 JSON 구조를 따라야 합니다:
{{
  "detected_speeches": [
    {{
      "speaker_name_raw": "...",
      "speaker_name_clean": "...",
      "speech_start_cue": "...",
      "is_real_person_guess": true,
      "is_substantial_discussion_guess": true
    }}
    // 추가 발언들...
  ]
}}
"""
    analyzed_statements_for_bill = []
    try:
        stage1_response = speaker_detection_llm.generate_content(
            speaker_detection_prompt)
        if not stage1_response or not stage1_response.text:
            logger.warning(
                f"❌ No response from LLM speaker detection for bill '{bill_name}'."
            )
            return []

        response_text_cleaned = stage1_response.text.strip().replace(
            "```json", "").replace("```", "").strip()

        try:
            stage1_data = json.loads(response_text_cleaned)
        except json.JSONDecodeError as e:
            logger.error(
                f"❌ JSON parsing error for speaker detection (bill '{bill_name}'): {e}. Response was: {response_text_cleaned}"
            )
            return []

        detected_speeches_info = stage1_data.get('detected_speeches', [])
        logger.info(
            f"✅ Speaker detection for '{bill_name}': Found {len(detected_speeches_info)} potential speech segments."
        )

        if not detected_speeches_info: return []

        # Iterate through detected speeches to extract and analyze full content
        for i, speech_info in enumerate(detected_speeches_info):
            clean_name = speech_info.get('speaker_name_clean')
            start_cue = speech_info.get('speech_start_cue')
            is_real_person = speech_info.get('is_real_person_guess', False)
            is_substantial = speech_info.get('is_substantial_discussion_guess',
                                             False)

            if not clean_name or not start_cue or not is_real_person or not is_substantial:
                logger.info(
                    f"Skipping speech segment for '{bill_name}' due to missing info or filters: Name='{clean_name}', Cue='{start_cue}', Person={is_real_person}, Substantial={is_substantial}"
                )
                continue

            # Find this speech's content using start_cue and look for next speech_start_cue or end of segment
            # The LLM gives us a CUE. We need to find this cue in the *original full bill_text_segment*
            current_speech_content = ""
            start_idx = bill_text_segment.find(start_cue)
            if start_idx == -1:
                logger.warning(
                    f"Could not find start_cue '{start_cue}' for speaker '{clean_name}' in bill_text_segment for '{bill_name}'. Skipping."
                )
                continue

            # Determine end of current speech:
            # Look for the start_cue of the *next* detected substantial speaker, or end of bill_text_segment.
            end_idx = len(bill_text_segment)  # Default to end of segment
            if i + 1 < len(detected_speeches_info):
                next_speech_info = detected_speeches_info[i + 1]
                next_start_cue = next_speech_info.get('speech_start_cue')
                if next_start_cue:
                    found_next_cue_at = bill_text_segment.find(
                        next_start_cue,
                        start_idx + 1)  # Search after current cue
                    if found_next_cue_at != -1:
                        end_idx = found_next_cue_at

            current_speech_content = bill_text_segment[
                start_idx:end_idx].strip()
            # Clean the extracted content
            current_speech_content = clean_pdf_text(current_speech_content)
            
            # Clean the extracted content a bit (remove the speaker part from the beginning if it was included by start_cue)
            # Example: if start_cue was "◯홍길동 의원 위원회에서는..." and speech is "◯홍길동 의원 위원회에서는..."
            # we want "위원회에서는..." for analysis. The prompt asks for speech_start_cue as the *beginning*.
            # The `extract_speech_between_markers` is better for this refined extraction.
            # Using simpler method for now based on cues
            if current_speech_content.startswith(
                    speech_info.get('speaker_name_raw', '')):
                current_speech_content = current_speech_content[
                    len(speech_info.get('speaker_name_raw', '')):].strip()
            elif current_speech_content.startswith(
                    start_cue):  # if start_cue includes the name
                # this logic is tricky, relies on good cues from LLM
                pass  # The cue itself IS the start of the text LLM saw.

            if not current_speech_content or len(
                    current_speech_content
            ) < 50:  # Min length for meaningful analysis
                logger.info(
                    f"Skipping short/empty speech by '{clean_name}' for '{bill_name}'."
                )
                continue

            logger.info(
                f"Analyzing content for '{clean_name}' on bill '{bill_name}' (approx {len(current_speech_content)} chars)."
            )
            # Analyze this specific speech content with bill context
            analysis_result_dict = analyze_single_statement_with_bill_context(
                {
                    'speaker_name': clean_name,
                    'text': current_speech_content
                }, session_id, bill_name, debug)
            if analysis_result_dict:
                analyzed_statements_for_bill.append(analysis_result_dict)

            if not debug: time.sleep(0.6)  # API rate limit

    except Exception as e:
        logger.error(
            f"❌ Error during speaker detection/analysis for bill '{bill_name}': {e}"
        )
        logger.exception("Full traceback for bill segment processing error:")

    logger.info(
        f"✅ Bill segment '{bill_name}' analysis resulted in {len(analyzed_statements_for_bill)} statements."
    )
    return analyzed_statements_for_bill


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

    # Limit text for LLM prompt
    prompt_text_limit = 7800  # For main model
    if len(text_to_analyze) > prompt_text_limit:
        logger.warning(
            f"Text for '{speaker_name}' on '{bill_name}' truncated from {len(text_to_analyze)} to {prompt_text_limit} for analysis."
        )
        text_for_prompt = text_to_analyze[:prompt_text_limit]
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
3.  **Policy Categories**: 발언의 주제를 가장 잘 나타내는 정책 분야를 선택합니다. 여러 분야에 걸칠 경우 가장 주요한 1~2개만 포함합니다. confidence는 해당 분류에 대한 모델의 확신도입니다.
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


def extract_statements_without_bill_separation(full_text,
                                               session_id,
                                               bills_context_str,
                                               debug=False):
    """Fallback: LLM speaker detection on full text, then individual analysis if no bill segmentation."""
    logger.info(
        f"🔄 Using full-text speaker detection for session: {session_id} (no bill segmentation)."
    )

    if not genai or not hasattr(genai, 'GenerativeModel'):
        logger.warning(
            "❌ Gemini API not configured. Cannot perform full-text speaker detection."
        )
        return []
    try:
        speaker_detection_model_name = 'gemini-2.0-flash-lite'  # Or 'gemini-2.0-flash-lite'
        speaker_detection_llm = genai.GenerativeModel(
            speaker_detection_model_name)
    except Exception as e_model:
        logger.error(
            f"Failed to initialize speaker detection model ({speaker_detection_model_name}): {e_model}"
        )
        return []

    prompt_text_limit = 7500
    if len(full_text) > prompt_text_limit:
        logger.warning(
            f"Full text for session {session_id} truncated for speaker detection prompt."
        )
        text_for_prompt = full_text[:prompt_text_limit]
    else:
        text_for_prompt = full_text

    speaker_detection_prompt = f"""
국회 전체 회의록 텍스트에서 국회의원들의 개별 발언을 식별해주세요.
회의에서 논의된 주요 의안 목록: {bills_context_str if bills_context_str else "제공되지 않음"}

회의록 텍스트 일부:
---
{text_for_prompt}
---

각 발언에 대해 다음 정보를 JSON 형식으로 제공해주세요. 배열 'detected_speeches' 안에 객체로 포함합니다:
{{
  "speaker_name_raw": "회의록 기록된 발언자 이름 원본 (예: 김철수의원)",
  "speaker_name_clean": "정리된 발언자 실명 (예: 김철수)",
  "speech_start_cue": "해당 발언이 시작되는 고유한 짧은 텍스트 조각 (회의록 원문에서 약 15-20자)",
  "is_real_person_guess": true/false,
  "is_substantial_discussion_guess": true/false
}}
(가이드라인은 extract_statements_for_bill_segment 와 동일하게 적용)

응답 JSON 구조:
{{
  "detected_speeches": [ /* ... */ ]
}}
"""
    all_analyzed_statements = []
    try:
        stage1_response = speaker_detection_llm.generate_content(
            speaker_detection_prompt)
        if not stage1_response or not stage1_response.text:
            logger.warning(
                f"No response from full-text speaker detection LLM for session {session_id}."
            )
            return []

        response_text_cleaned = stage1_response.text.strip().replace(
            "```json", "").replace("```", "").strip()
        stage1_data = json.loads(response_text_cleaned)
        detected_speeches_info = stage1_data.get('detected_speeches', [])
        logger.info(
            f"Full-text speaker detection for session {session_id}: Found {len(detected_speeches_info)} potential speech segments."
        )

        if not detected_speeches_info: return []

        for i, speech_info in enumerate(detected_speeches_info):
            # Similar extraction and analysis logic as in extract_statements_for_bill_segment
            clean_name = speech_info.get('speaker_name_clean')
            start_cue = speech_info.get('speech_start_cue')
            is_real_person = speech_info.get('is_real_person_guess', False)
            is_substantial = speech_info.get('is_substantial_discussion_guess',
                                             False)

            if not clean_name or not start_cue or not is_real_person or not is_substantial:
                continue  # Skip if basic filters fail

            start_idx = full_text.find(start_cue)
            if start_idx == -1: continue

            end_idx = len(full_text)
            if i + 1 < len(detected_speeches_info):
                next_start_cue = detected_speeches_info[i + 1].get(
                    'speech_start_cue')
                if next_start_cue:
                    found_next_cue_at = full_text.find(next_start_cue,
                                                       start_idx + 1)
                    if found_next_cue_at != -1: end_idx = found_next_cue_at

            current_speech_content = full_text[start_idx:end_idx].strip()
            # Clean the extracted content
            current_speech_content = clean_pdf_text(current_speech_content)
            
            # Clean content similar to bill_segment version
            if current_speech_content.startswith(
                    speech_info.get('speaker_name_raw', '')):
                current_speech_content = current_speech_content[
                    len(speech_info.get('speaker_name_raw', '')):].strip()

            if not current_speech_content or len(current_speech_content) < 50:
                continue

            # For full text extraction, bill context is more general. We use `analyze_single_statement` (no bill_name)
            # or pass a generic "General Discussion" or the bills_context_str as bill_name.
            # Here, we'll use analyze_single_statement which doesn't take bill_name explicitly.
            analysis_result_dict = analyze_single_statement(  # Uses simpler analysis
                {
                    'speaker_name': clean_name,
                    'text': current_speech_content
                }, session_id, debug)
            if analysis_result_dict:  # analyze_single_statement should return a dict
                # We might want to add a general 'associated_bill_name' here if schema expects it.
                analysis_result_dict[
                    'associated_bill_name'] = "General Discussion / Full Transcript"
                all_analyzed_statements.append(analysis_result_dict)

            if not debug: time.sleep(0.6)

    except json.JSONDecodeError as e:
        logger.error(
            f"JSON parsing error in full-text speaker detection (session {session_id}): {e}. Response: {response_text_cleaned if 'response_text_cleaned' in locals() else 'N/A'}"
        )
    except Exception as e:
        logger.error(
            f"❌ Error in full-text statement extraction (session {session_id}): {e}"
        )
        logger.exception("Full traceback for full-text extraction error:")

    logger.info(
        f"✅ Full-text LLM extraction for session {session_id} completed: {len(all_analyzed_statements)} statements."
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
    prompt_text_limit = 7800
    if len(text_to_analyze) > prompt_text_limit:
        text_for_prompt = text_to_analyze[:prompt_text_limit]
    else:
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
        # prompt_text_limit = 7800 For segmentation model context
        # text_for_seg_prompt = full_text
        '''
        if len(full_text) > prompt_text_limit:
            text_for_seg_prompt = full_text[:prompt_text_limit] # Use beginning of text for segmentation cues
            logger.warning(f"Full text for session {session_id} truncated for bill segmentation prompt.")
            '''

        bill_segmentation_prompt = f"""
국회 회의록 전체 텍스트에서 논의된 주요 의안(법안)별로 구간을 나누어주세요.
다음은 이 회의에서 논의된 의안 목록입니다: {", ".join(bill_names_list)}

회의록 텍스트 (일부):
---
{full_text}
---

각 의안에 대한 논의 시작 지점을 알려주세요. JSON 형식 응답:
{{
  "bill_discussion_segments": [
    {{
      "bill_name_identified": "LLM이 식별한 의안명 (목록에 있는 이름과 최대한 일치)",
      "discussion_start_cue": "해당 의안 논의가 시작되는 회의록 내 고유한 텍스트 조각 (약 20-30자)",
      "relevance_to_provided_list": 0.0-1.0 (제공된 의안 목록과의 관련성 추정치)
    }}
  ],
  "general_discussion_cue": "특정 의안에 해당하지 않는 일반 토론 시작 지점 (있을 경우, 20-30자 텍스트 조각)"
}}

- "bill_name_identified"는 제공된 의안 목록에 있는 이름 중 하나와 일치하거나 매우 유사해야 합니다.
- "discussion_start_cue"는 회의록 원문에서 가져와야 하며, 이를 기준으로 텍스트를 나눌 것입니다.
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

    # Sort segments by their appearance order in the full_text using their cues
    # This assumes cues are unique and appear in order
    sorted_segments_with_text = []
    if bill_segments_from_llm:
        valid_segments_for_sort = []
        for seg_info in bill_segments_from_llm:
            cue = seg_info.get("discussion_start_cue")
            if cue:
                idx = full_text.find(cue)
                if idx != -1:
                    seg_info['start_index'] = idx
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
            "No bill segments identified or processed. Processing PDF text as a single unit."
        )
        # This function returns list of DICTS (speaker, text, LLM analysis fields)
        all_extracted_statements_data = extract_statements_without_bill_separation(
            full_text, session_id, bills_context_str, debug)

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

            # Ensure Django DB connection is alive, esp. in long tasks
            from django.db import connection
            connection.ensure_connection()

            speaker_obj = get_or_create_speaker(
                speaker_name,
                debug=debug)  # Debug here should match overall debug
            if not speaker_obj:
                logger.warning(
                    f"⚠️ Could not get/create speaker: {speaker_name}. Skipping statement."
                )
                continue

            # Check for existing identical statement (text, speaker, session) to avoid duplicates from reprocessing
            if Statement.objects.filter(session=session_obj,
                                        speaker=speaker_obj,
                                        text_hash=Statement.calculate_hash(
                                            statement_text, speaker_obj.naas_cd, session_obj.conf_id)).exists():
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
                    # Prefer exact match if possible, or high-confidence partial
                    associated_bill_obj = Bill.objects.filter(
                        session=session_obj,
                        bill_nm__iexact=assoc_bill_name_from_data).first()
                    if not associated_bill_obj:
                        # Fallback to icontains if exact name might have variations from LLM
                        # Be cautious with icontains if bill names are very similar
                        bill_candidates = Bill.objects.filter(
                            session=session_obj,
                            bill_nm__icontains=assoc_bill_name_from_data.split(
                                '(')[0].strip())  # Match before parenthesis
                        if bill_candidates.count() == 1:
                            associated_bill_obj = bill_candidates.first()
                        elif bill_candidates.count() > 1:
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
            new_statement.save(
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


def extract_statements_with_llm_validation(full_text,
                                           session_id,
                                           bills_context_str,
                                           debug=False):
    """
    DEPRECATED-LIKE / Refactored into process_pdf_text_for_statements which orchestrates segmentation.
    This was an older top-level entry point. Calls will now go to `process_pdf_text_for_statements`.
    If called directly, it implies full-text processing without segmentation attempt.
    """
    logger.warning(
        "`extract_statements_with_llm_validation` called directly. Processing full text without segmentation attempt."
    )
    if not model:
        logger.warning(
            "❌ LLM model not available, using very basic regex fallback if any."
        )
        # return extract_statements_with_regex_fallback(full_text, session_id, debug) # This fallback also needs LLM or heavy rework
        return []

    return extract_statements_without_bill_separation(full_text, session_id,
                                                      bills_context_str, debug)


def extract_speech_between_markers(full_text,
                                   exact_start_marker,
                                   next_speaker_char_cue="◯",
                                   speaker_name_for_log="Unknown"):
    """
    Extract speech content for a given speaker.
    - full_text: The larger text block (e.g., a bill segment or whole transcript).
    - exact_start_marker: The precise text indicating the current speaker's turn (e.g., "◯김부겸 국무총리").
    - next_speaker_char_cue: Character(s) indicating start of ANY next speaker (e.g., "◯").
    - speaker_name_for_log: For logging.
    """
    try:
        if not full_text or not exact_start_marker:
            return ""

        start_pos = full_text.find(exact_start_marker)
        if start_pos == -1:
            logger.warning(
                f"Could not find exact_start_marker '{exact_start_marker}' for {speaker_name_for_log}."
            )
            return ""

        # Content begins *after* the marker typically, if marker includes speaker name
        # If marker is *just* the name and "◯", then text is after that.
        # This function assumes 'exact_start_marker' *is* the beginning of the speech content to be returned.
        # So, content_actual_start = start_pos.

        # Find where this speaker's content ends: at the start of the next speaker's cue OR end of full_text
        end_pos_of_current_speech = len(full_text)

        # Search for the next_speaker_char_cue *after* the beginning of the current speaker's marker
        # This prevents finding the current speaker's own cue.
        search_for_next_cue_from = start_pos + len(
            exact_start_marker)  # Search AFTER the current marker text
        if search_for_next_cue_from >= len(
                full_text):  # If current marker is at the very end
            search_for_next_cue_from = start_pos + 1  # At least search 1 char after current marker's start

        next_cue_pos = full_text.find(next_speaker_char_cue,
                                      search_for_next_cue_from)

        if next_cue_pos != -1:
            end_pos_of_current_speech = next_cue_pos

        speech_content = full_text[start_pos:end_pos_of_current_speech].strip()

        # Further cleaning: remove speaker name tag from beginning of *extracted* content IF NECESSARY.
        # This depends on how 'exact_start_marker' is defined. If it IS "◯Speaker Name Actual Speech...",
        # then the below cleaning might not be needed as the 'Actual Speech' part is already isolated.
        # However, prompts usually ask for speaker + a bit of text as a cue.

        # Minimalist cleaning, more robust cleaning specific to format might be needed
        # Remove parenthetical asides common in transcripts
        import re
        speech_content_cleaned = re.sub(
            r'\s*\([^)]*\)\s*', ' ',
            speech_content)  # remove (text) and surrounding spaces
        speech_content_cleaned = re.sub(
            r'\s+', ' ',
            speech_content_cleaned).strip()  # Consolidate multiple spaces

        return speech_content_cleaned

    except Exception as e:
        logger.error(
            f"❌ Error in extract_speech_between_markers for '{speaker_name_for_log}': {e}"
        )
        return ""


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

    prompt_text_limit = 7800
    if len(text_to_analyze) > prompt_text_limit:
        text_for_prompt = text_to_analyze[:prompt_text_limit]
    else:
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


def parse_and_analyze_statements_from_text(full_text,
                                           session_id,
                                           bills_context_str,
                                           debug=False):
    """
    DEPRECATED-LIKE / Refactored. This was an older mid-level orchestrator.
    New main entry point for PDF text processing is `process_pdf_text_for_statements`.
    If this is called, it suggests a less granular approach (full text processing).
    """
    logger.warning(
        "`parse_and_analyze_statements_from_text` called. "
        "This implies processing full text without bill segmentation attempt. "
        "Consider calling `process_pdf_text_for_statements` instead.")

    # This directly calls the full-text extraction and analysis path
    statements_data = extract_statements_without_bill_separation(
        full_text, session_id, bills_context_str, debug)
    # The `extract_statements_without_bill_separation` now returns already analyzed data (list of dicts).
    # No further loop for `analyze_single_statement` is needed here if that's true.

    logger.info(
        f"✅ Full-text parsing and analysis yielded {len(statements_data)} statements for session {session_id}."
    )
    return statements_data  # Returns list of dicts with analysis


def create_statement_categories(statement_obj,
                                policy_categories_list_from_llm):
    """Create/update Category, Subcategory, and StatementCategory associations for a Statement."""
    if not statement_obj or not policy_categories_list_from_llm:
        return

    from .models import Category, Subcategory, StatementCategory  # Ensure models are importable

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
            category_obj, _ = Category.objects.get_or_create(
                name=main_cat_name,
                defaults={'description': f'{main_cat_name} 관련 정책'})

            subcategory_obj = None
            if sub_cat_name and sub_cat_name.lower(
            ) != '일반' and sub_cat_name.lower() != '없음':
                subcategory_obj, _ = Subcategory.objects.get_or_create(
                    name=sub_cat_name,
                    category=category_obj,  # Associate with parent category
                    defaults={
                        'description':
                        f'{sub_cat_name} 관련 세부 정책 ({main_cat_name})'
                    })

            # Create or update StatementCategory link
            StatementCategory.objects.update_or_create(
                statement=statement_obj,
                category=category_obj,
                subcategory=
                subcategory_obj,  # Can be None if no specific subcategory
                defaults={'confidence_score': confidence})
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
    # Optional: Basic title stripping if LLM missed it or raw name is used
    # common_titles = ["의원", "위원장", "장관", "의장", "후보자", "대통령"] # etc.
    # for title in common_titles:
    #     if speaker_name_cleaned.endswith(title):
    #         speaker_name_cleaned = speaker_name_cleaned[:-len(title)].strip()

    if not speaker_name_cleaned:  # If stripping resulted in empty name
        logger.warning(
            f"Speaker name '{speaker_name_raw}' became empty after cleaning.")
        return None

    try:
        from django.db import connection  # Ensure connection for long tasks
        connection.ensure_connection()

        # Try to find by exact cleaned name first
        speaker_obj = Speaker.objects.filter(
            naas_nm=speaker_name_cleaned).first()

        if speaker_obj:
            if debug:
                logger.debug(f"Found existing speaker: {speaker_name_cleaned}")
            return speaker_obj

        # If not found by exact name, try case-insensitive and containing (more risky for ambiguity)
        # speaker_obj = Speaker.objects.filter(naas_nm__icontains=speaker_name_cleaned).first() # Use with caution
        # if speaker_obj:
        #     logger.info(f"Found speaker by icontains: {speaker_name_raw} -> {speaker_obj.naas_nm}. Using this.")
        #     return speaker_obj

        # If still not found, this speaker is new to our DB.
        # Attempt to fetch full details from API.
        logger.info(
            f"Speaker '{speaker_name_cleaned}' not found in DB. Attempting to fetch details from API."
        )

        # `fetch_speaker_details` tries to get/create from API and returns the Speaker object.
        # This function should be robust and handle API failures.
        # It's not a Celery task itself in this definition.
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

    except Exception as e:
        logger.error(
            f"❌ Error in get_or_create_speaker for '{speaker_name_raw}': {e}")
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