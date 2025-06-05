import requests
import pdfplumber
from celery import shared_task
from django.conf import settings
from .models import Session, Bill, Speaker, Statement
from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import RequestException
import logging
from celery.schedules import crontab
from datetime import datetime, timedelta
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

    if debug:
        print(
            f"🐛 DEBUG MODE: Processing {len(sessions_data)} sessions (preview only - no database writes)"
        )
        logger.info(
            f"🐛 DEBUG MODE: Processing {len(sessions_data)} sessions (preview only - no database writes)"
        )
        for i, row in enumerate(sessions_data[:10],
                                1):  # Show first 10 sessions
            session_id = row.get('CONFER_NUM')
            title = row.get('TITLE', 'Unknown')
            date = row.get('CONF_DATE', 'Unknown')
            pdf_url = row.get('PDF_LINK_URL', 'No PDF')

            print(f"🐛 DEBUG Session {i}: ID={session_id}")
            print(f"   Title: {title}")
            print(f"   Date: {date}")
            print(f"   PDF: {pdf_url}")
            print(f"   All available keys: {list(row.keys())}")
            print(f"   Full data: {row}")
            print("   ---")

            logger.info(f"🐛 DEBUG Session {i}: ID={session_id}")
            logger.info(f"   Title: {title}")
            logger.info(f"   Date: {date}")
            logger.info(f"   PDF: {pdf_url}")
            logger.info(f"   All available keys: {list(row.keys())}")
            logger.info(f"   Full data: {row}")
            logger.info("   ---")

        if len(sessions_data) > 10:
            print(f"🐛 DEBUG: ... and {len(sessions_data) - 10} more sessions")
            logger.info(
                f"🐛 DEBUG: ... and {len(sessions_data) - 10} more sessions")
        print("🐛 DEBUG MODE: Data preview completed - not storing to database")
        logger.info(
            "🐛 DEBUG MODE: Data preview completed - not storing to database")
        return

    created_count = 0
    updated_count = 0

    for i, row in enumerate(sessions_data, 1):
        try:
            logger.info(
                f"🔄 Processing session {i}/{len(sessions_data)}: {row.get('TITLE', 'Unknown')}"
            )

            # Use CONFER_NUM as the proper session ID
            session_id = row.get('CONFER_NUM')
            if not session_id:
                logger.warning(f"⚠️ No CONFER_NUM found for session {i}")
                continue

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
                    row.get('CONF_DATE', ''),
                    'conf_knd':
                    row.get('CLASS_NAME', '국회본회의'),
                    'cmit_nm':
                    row.get('CLASS_NAME', '국회본회의'),
                    'bg_ptm':
                    '',  # Not available in this API
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
                session.conf_dt = row.get('CONF_DATE', '')
                session.conf_knd = row.get('CLASS_NAME', '국회본회의')
                session.cmit_nm = row.get('CLASS_NAME', '국회본회의')
                session.down_url = row.get('PDF_LINK_URL', '')
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
            "CONF_ID": session_id
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
            logger.warning(f"❌ No details found for session {session_id}")
            logger.info(f"📋 Full API response: {data}")

            # Try to fetch bills anyway, some sessions might have bills without detailed info
            if is_celery_available():
                fetch_session_bills.delay(session_id, force=force, debug=debug)
            else:
                fetch_session_bills(session_id=session_id,
                                    force=force,
                                    debug=debug)
            return

        logger.info(f"✅ Found session details for: {session_id}")
        session = Session.objects.get(conf_id=session_id)

        # Update session details if available
        if session_details.get('DOWN_URL'):
            session.down_url = session_details['DOWN_URL']
            session.save()
            logger.info(f"📄 Updated PDF URL for session: {session_id}")

        # Fetch bills for this session (with fallback)
        if is_celery_available():
            fetch_session_bills.delay(session_id, force=force, debug=debug)
        else:
            fetch_session_bills(session_id=session_id,
                                force=force,
                                debug=debug)

        # Process PDF if URL is available (with fallback)
        if session.down_url:
            if is_celery_available():
                process_session_pdf.delay(session_id, force=force, debug=debug)
            else:
                process_session_pdf(session_id=session_id,
                                    force=force,
                                    debug=debug)

    except (RequestException, Session.DoesNotExist) as e:
        logger.error(f"Error fetching session details: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for fetch_session_details: {session_id}"
                )
                raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self=None, session_id=None, force=False, debug=False):
    """Fetch bills discussed in a specific session."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Fetching bills for session {session_id} in debug mode"
            )
            # Continue with actual API call in debug mode
        url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": session_id
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        session = Session.objects.get(conf_id=session_id)

        for row in data.get('row', []):
            bill, created = Bill.objects.get_or_create(bill_id=row['BILL_ID'],
                                                       session=session,
                                                       defaults={
                                                           'bill_nm':
                                                           row['BILL_NM'],
                                                           'link_url':
                                                           row['LINK_URL']
                                                       })

            # If bill exists and force is True, update the bill
            if not created and force:
                bill.bill_nm = row['BILL_NM']
                bill.link_url = row['LINK_URL']
                bill.save()

    except (RequestException, Session.DoesNotExist) as e:
        logger.error(f"Error fetching session bills: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for fetch_session_bills: {session_id}"
                )
                raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self=None, session_id=None, force=False, debug=False):
    """Download and process PDF for a session."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Skipping PDF processing for session {session_id} in debug mode (too resource intensive)"
            )
            return
        session = Session.objects.get(conf_id=session_id)

        # Skip if PDF already processed and not forcing
        if not force and session.statements.exists():
            logger.info(f"Session {session_id} already processed, skipping")
            return

        # Create temp directory if it doesn't exist
        temp_dir = Path("temp")
        temp_dir.mkdir(exist_ok=True)
        pdf_path = temp_dir / f"temp_{session_id}.pdf"

        # Download PDF
        response = requests.get(session.down_url, timeout=30)
        response.raise_for_status()

        with open(pdf_path, 'wb') as f:
            f.write(response.content)

        # Extract text from PDF
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""

        # Process text and extract statements (with fallback)
        if is_celery_available():
            process_statements.delay(session_id,
                                     text,
                                     force=force,
                                     debug=debug)
        else:
            process_statements(session_id=session_id,
                               text=text,
                               force=force,
                               debug=debug)

        # Clean up
        os.remove(pdf_path)

    except (RequestException, Session.DoesNotExist, Exception) as e:
        logger.error(f"Error processing session PDF: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for process_session_pdf: {session_id}"
                )
                raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_statements(self=None,
                       session_id=None,
                       text=None,
                       force=False,
                       debug=False):
    """Process extracted text and analyze sentiments."""
    try:
        if debug:
            logger.info(
                f"🐛 DEBUG: Skipping statement processing for session {session_id} in debug mode (too resource intensive)"
            )
            if text:
                logger.info(f"🐛 DEBUG: Text preview: {text[:200]}...")
            return
        session = Session.objects.get(conf_id=session_id)

        # Skip if statements already processed and not forcing
        if not force and session.statements.exists():
            logger.info(
                f"Statements for session {session_id} already processed, skipping"
            )
            return

        # Split text into statements (this is a simplified version)
        statements = text.split('\n\n')

        # Rate limiting: 30 requests per 60 seconds = 1 request every 2 seconds
        request_delay = 2.1  # Slightly more than 2 seconds to be safe

        for i, statement in enumerate(statements):
            if not statement.strip():
                continue

            try:
                # Add rate limiting delay
                if i > 0:  # Don't delay the first request
                    time.sleep(request_delay)

                # Use Gemini to analyze the statement
                if not model:
                    logger.warning(
                        "Gemini model not available, skipping sentiment analysis"
                    )
                    continue

                prompt = f"""
                Analyze the following statement from a National Assembly meeting:
                
                {statement}
                
                Please provide:
                1. The speaker's name and party
                2. A sentiment score from -1 (very negative) to 1 (very positive)
                3. A brief explanation for the sentiment score
                
                Format the response as JSON:
                {{
                    "speaker": {{
                        "name": "name",
                        "party": "party"
                    }},
                    "sentiment_score": score,
                    "reason": "explanation"
                }}
                """

                response = model.generate_content(prompt)
                result = response.text

                # Parse the result and create Statement object
                data = json.loads(result)
                speaker, _ = Speaker.objects.get_or_create(
                    naas_nm=data['speaker']['name'],
                    defaults={'plpt_nm': data['speaker']['party']})

                Statement.objects.create(
                    session=session,
                    speaker=speaker,
                    text=statement,
                    sentiment_score=data['sentiment_score'],
                    sentiment_reason=data['reason'])

                logger.info(
                    f"Processed statement {i+1}/{len(statements)} for session {session_id}"
                )

            except Exception as e:
                logger.error(f"Error processing individual statement: {e}")
                continue

    except (Session.DoesNotExist, Exception) as e:
        logger.error(f"Error processing statements: {e}")
        if self:
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error(
                    f"Max retries exceeded for process_statements: {session_id}"
                )
                raise


# Scheduled task to run daily at midnight
@shared_task
def scheduled_data_collection(debug=False):
    """Scheduled task to collect data daily."""
    logger.info(f"Starting scheduled data collection (debug={debug})")
    if is_celery_available():
        fetch_latest_sessions.delay(force=False, debug=debug)
    else:
        fetch_latest_sessions(force=False, debug=debug)
    logger.info("Scheduled data collection completed")
