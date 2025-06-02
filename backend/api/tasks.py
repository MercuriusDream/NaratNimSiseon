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
from pathlib import Path

logger = logging.getLogger(__name__)

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_latest_sessions(self, force=False):
    """Fetch latest assembly sessions from the API."""
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
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('row'):
            logger.warning("No sessions found in API response")
            return
        
        for row in data['row']:
            try:
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
                    }
                )
                
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
                
                # Queue session details fetch
                fetch_session_details.delay(session_id, force=force)
                
            except Exception as e:
                logger.error(f"Error processing session row: {e}")
                continue
                
    except RequestException as e:
        logger.error(f"Error fetching sessions: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error("Max retries exceeded for fetch_latest_sessions")
            raise

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_details(self, session_id, force=False):
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
            logger.warning(f"No details found for session {session_id}")
            return
            
        session_data = data['row'][0]
        session = Session.objects.get(conf_id=session_id)
        
        # Update session details
        session.down_url = session_data['DOWN_URL']
        session.save()
        
        # Fetch bills for this session
        fetch_session_bills.delay(session_id, force=force)
        
        # Process PDF if URL is available
        if session.down_url:
            process_session_pdf.delay(session_id, force=force)
        
    except (RequestException, Session.DoesNotExist) as e:
        logger.error(f"Error fetching session details: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for fetch_session_details: {session_id}")
            raise

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self, session_id, force=False):
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
            bill, created = Bill.objects.get_or_create(
                bill_id=row['BILL_ID'],
                session=session,
                defaults={
                    'bill_nm': row['BILL_NM'],
                    'link_url': row['LINK_URL']
                }
            )
            
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
            logger.error(f"Max retries exceeded for fetch_session_bills: {session_id}")
            raise

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_session_pdf(self, session_id, force=False):
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
        
        # Process text and extract statements
        process_statements.delay(session_id, text, force=force)
        
        # Clean up
        os.remove(pdf_path)
        
    except (RequestException, Session.DoesNotExist, Exception) as e:
        logger.error(f"Error processing session PDF: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for process_session_pdf: {session_id}")
            raise

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_statements(self, session_id, text, force=False):
    """Process extracted text and analyze sentiments."""
    try:
        session = Session.objects.get(conf_id=session_id)
        
        # Skip if statements already processed and not forcing
        if not force and session.statements.exists():
            logger.info(f"Statements for session {session_id} already processed, skipping")
            return
        
        # Split text into statements (this is a simplified version)
        statements = text.split('\n\n')
        
        for statement in statements:
            if not statement.strip():
                continue
                
            try:
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
                    defaults={'plpt_nm': data['speaker']['party']}
                )
                
                Statement.objects.create(
                    session=session,
                    speaker=speaker,
                    text=statement,
                    sentiment_score=data['sentiment_score'],
                    sentiment_reason=data['reason']
                )
            except Exception as e:
                logger.error(f"Error processing individual statement: {e}")
                continue
                
    except (Session.DoesNotExist, Exception) as e:
        logger.error(f"Error processing statements: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for process_statements: {session_id}")
            raise

# Scheduled task to run daily at midnight
@shared_task
def scheduled_data_collection():
    """Scheduled task to collect data daily."""
    logger.info("Starting scheduled data collection")
    fetch_latest_sessions.delay(force=False)
    logger.info("Scheduled data collection completed") 