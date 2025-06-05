import requests
import pdfplumber
import google.generativeai as genai
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

logger = logging.getLogger(__name__)

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemma-3-27b-it')


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
def fetch_latest_sessions(self=None, force=False):
    """Fetch latest assembly sessions from the API."""
    logger.info(f"🔍 Starting session fetch (force={force})")
    try:
        url = "https://open.assembly.go.kr/portal/openapi/nekcaiymatialqlxr"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "pIndex": 1,
            "pSize": 100,
            "UNIT_CD": "100022"  # 22nd Assembly
        }

        # If not force, only fetch sessions from the last 24 hours
        if not force:
            yesterday = datetime.now() - timedelta(days=1)
            params['MEETING_DATE'] = yesterday.strftime('%Y%m%d')
            logger.info(
                f"📅 Fetching sessions since: {yesterday.strftime('%Y%m%d')}")
        else:
            logger.info("🔄 Force mode: Fetching ALL sessions")

        logger.info(f"🌐 API URL: {url}")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        logger.info(
            f"📊 API Response structure: {list(data.keys()) if data else 'Empty response'}"
        )

        # Handle the nested structure: data['nekcaiymatialqlxr'][1]['row']
        # Note: [0] contains metadata, [1] contains actual row data
        sessions_data = None
        if 'nekcaiymatialqlxr' in data and len(data['nekcaiymatialqlxr']) > 1:
            sessions_data = data['nekcaiymatialqlxr'][1].get('row', [])
        elif 'nekcaiymatialqlxr' in data and len(
                data['nekcaiymatialqlxr']) > 0:
            # Try first element as fallback
            sessions_data = data['nekcaiymatialqlxr'][0].get('row', [])
        elif 'row' in data:
            # Fallback for old API structure
            sessions_data = data['row']

        if not sessions_data:
            logger.warning("❌ No sessions found in API response")
            logger.info(f"📋 Full API response: {data}")
            return

        logger.info(f"✅ Found {len(sessions_data)} sessions in API response")

        created_count = 0
        updated_count = 0

        for i, row in enumerate(sessions_data, 1):
            try:
                logger.info(
                    f"🔄 Processing session {i}/{len(sessions_data)}: {row.get('MEETINGSESSION', 'Unknown')}"
                )
                session_id = f"{row['MEETINGSESSION']}_{row['CHA']}"
                session, created = Session.objects.get_or_create(
                    conf_id=session_id,
                    defaults={
                        'era_co': '제22대',
                        'sess': row['MEETINGSESSION'],
                        'dgr': row['CHA'],
                        'conf_dt': row['MEETTING_DATE'],
                        'conf_knd': '국회본회의',
                        'cmit_nm': '국회본회의',
                        'bg_ptm': row['MEETTING_TIME'],
                        'down_url': row['LINK_URL']
                    })

                if created:
                    created_count += 1
                    logger.info(f"✨ Created new session: {session_id}")
                else:
                    logger.info(f"♻️  Session already exists: {session_id}")

                # If session exists and force is True, update the session
                if not created and force:
                    session.era_co = '제22대'
                    session.sess = row['MEETINGSESSION']
                    session.dgr = row['CHA']
                    session.conf_dt = row['MEETTING_DATE']
                    session.conf_knd = '국회본회의'
                    session.cmit_nm = '국회본회의'
                    session.bg_ptm = row['MEETTING_TIME']
                    session.down_url = row['LINK_URL']
                    session.save()
                    updated_count += 1
                    logger.info(f"🔄 Updated existing session: {session_id}")

                # Queue session details fetch (with fallback)
                if is_celery_available():
                    fetch_session_details.delay(session_id, force=force)
                    logger.info(f"📋 Queued details fetch for: {session_id}")
                else:
                    fetch_session_details(session_id=session_id, force=force)
                    logger.info(f"📋 Processed details fetch for: {session_id}")

            except Exception as e:
                logger.error(f"❌ Error processing session row {i}: {e}")
                continue

        logger.info(
            f"🎉 Session fetch completed: {created_count} created, {updated_count} updated"
        )

    except Exception as e:
        logger.error(f"❌ Critical error in fetch_latest_sessions: {e}")
        logger.error(f"📊 Session count in DB: {Session.objects.count()}")
        raise

    except RequestException as e:
        logger.error(f"Error fetching sessions: {e}")
        if self:  # Only retry if running as Celery task
            try:
                self.retry(exc=e)
            except MaxRetriesExceededError:
                logger.error("Max retries exceeded for fetch_latest_sessions")
                raise
        else:
            logger.error("Sync execution failed, no retry available")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_details(self=None, session_id=None, force=False):
    """Fetch detailed information for a specific session."""
    try:
        url = "https://open.assembly.go.kr/portal/openapi/VCONFDETAIL"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": session_id
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not data.get('row'):
            print(session_id)
            print(data)
            logger.warning(f"No details found for session {session_id}")
            return

        session_data = data['row'][0]
        session = Session.objects.get(conf_id=session_id)

        # Update session details
        session.down_url = session_data['DOWN_URL']
        session.save()

        # Fetch bills for this session (with fallback)
        if is_celery_available():
            fetch_session_bills.delay(session_id, force=force)
        else:
            fetch_session_bills(session_id=session_id, force=force)

        # Process PDF if URL is available (with fallback)
        if session.down_url:
            if is_celery_available():
                process_session_pdf.delay(session_id, force=force)
            else:
                process_session_pdf(session_id=session_id, force=force)

    except (RequestException, Session.DoesNotExist) as e:
        logger.error(f"Error fetching session details: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for fetch_session_details: {session_id}"
            )
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self=None, session_id=None, force=False):
    """Fetch bills discussed in a specific session."""
    try:
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
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for fetch_session_bills: {session_id}")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self=None, session_id=None, force=False):
    """Download and process PDF for a session."""
    try:
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
            process_statements.delay(session_id, text, force=force)
        else:
            process_statements(session_id=session_id, text=text, force=force)

        # Clean up
        os.remove(pdf_path)

    except (RequestException, Session.DoesNotExist, Exception) as e:
        logger.error(f"Error processing session PDF: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for process_session_pdf: {session_id}")
            raise


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_statements(self=None, session_id=None, text=None, force=False):
    """Process extracted text and analyze sentiments."""
    try:
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
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"Max retries exceeded for process_statements: {session_id}")
            raise


# Scheduled task to run daily at midnight
@shared_task
def scheduled_data_collection():
    """Scheduled task to collect data daily."""
    logger.info("Starting scheduled data collection")
    fetch_latest_sessions.delay(force=False)
    logger.info("Scheduled data collection completed")
