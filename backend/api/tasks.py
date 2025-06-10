import requests
import pdfplumber
import io
import logging
import json
import time
import threading
import re
from collections import deque
from functools import wraps
from datetime import datetime, timedelta, time as dt_time

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings
from django.db import connections, OperationalError, transaction
from google.api_core import exceptions as google_exceptions
from google import genai
from google.genai import types
from requests.exceptions import RequestException

from .models import (Session, Bill, Speaker, Statement, Party, VotingRecord,
                     Category, Subcategory, BillCategoryMapping,
                     BillSubcategoryMapping)

# Standard Python logger
logger = logging.getLogger(__name__)

# --- Configuration ---
ENABLE_VOTING_DATA_COLLECTION = True


# --- Database Retry Decorator ---
def with_db_retry(max_retries=3):
    """A decorator to retry database operations on OperationalError."""

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    for conn in connections.all():
                        conn.close_if_unusable_or_obsolete()
                    with transaction.atomic():
                        return func(*args, **kwargs)
                except OperationalError as e:
                    if attempt == max_retries - 1:
                        logger.error(
                            f"DB operation '{func.__name__}' failed after {max_retries} attempts: {e}"
                        )
                        raise
                    wait_time = (2**attempt) * 0.1
                    logger.warning(
                        f"DB operation '{func.__name__}' failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
            return None

        return wrapper

    return decorator


# --- The One True GeminiHandler ---
class GeminiHandler:
    """Final, unified handler for all Gemini API interactions."""

    def __init__(self,
                 api_key,
                 model_name='gemini-1.5-flash-latest',
                 max_requests_per_minute=15):
        self.logger = logger
        self.model_name = model_name
        self.api_key = api_key
        if not self.api_key:
            self.logger.critical(
                "FATAL: GeminiHandler initialized with NULL API key. Client offline."
            )
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        self.max_requests_per_minute = max_requests_per_minute
        self.request_times = deque()
        self.lock = threading.Lock()
        self.consecutive_errors = 0
        self.backoff_until = None

    def _wait_if_needed(self):
        with self.lock:
            if self.backoff_until and datetime.now() < self.backoff_until:
                wait_time = (self.backoff_until -
                             datetime.now()).total_seconds()
                self.logger.warning(
                    f"In exponential backoff. Waiting for {wait_time:.1f}s.")
                time.sleep(wait_time)
            while True:
                now = datetime.now()
                one_minute_ago = now - timedelta(minutes=1)
                while self.request_times and self.request_times[
                        0] < one_minute_ago:
                    self.request_times.popleft()
                if len(self.request_times) < self.max_requests_per_minute:
                    return True
                wait_duration = (self.request_times[0] + timedelta(minutes=1) -
                                 now).total_seconds()
                self.logger.info(
                    f"RPM limit reached. Waiting for {wait_duration:.1f}s")
                time.sleep(max(0, wait_duration) + 0.1)

    def _record_request(self, success=True):
        with self.lock:
            if success:
                self.request_times.append(datetime.now())
                self.consecutive_errors = 0
                self.backoff_until = None
            else:
                self.consecutive_errors += 1
                backoff_seconds = min(60, 2**self.consecutive_errors)
                self.backoff_until = datetime.now() + timedelta(
                    seconds=backoff_seconds)
                self.logger.warning(
                    f"API error recorded. Backing off for {backoff_seconds}s.")

    def execute_api_call(self, contents, retries=3):
        if not self.client:
            self.logger.error(
                "API call aborted; Gemini client not initialized.")
            return None
        for attempt in range(retries):
            self._wait_if_needed()
            try:
                response = self.client.models.generate_content(
                    model=self.model_name, contents=contents)
                self._record_request(success=True)
                return response
            except (google_exceptions.ResourceExhausted,
                    google_exceptions.InternalServerError,
                    google_exceptions.ServiceUnavailable) as e:
                self.logger.warning(
                    f"Retriable API error on attempt {attempt+1}: {e}")
                self._record_request(success=False)
            except Exception as e:
                self.logger.error(f"Non-retriable Gemini API error: {e}",
                                  exc_info=True)
                self._record_request(success=False)
                break
        self.logger.error(
            f"Failed to call Gemini API after {retries} attempts.")
        return None


# --- Singleton Instantiation ---
GEMINI = GeminiHandler(api_key=getattr(settings, 'GEMINI_API_KEY', None))


# --- Utility Functions ---
def format_conf_id(conf_id):
    return str(conf_id).replace('N', '').strip().zfill(6)


def extract_sessions_from_response(data, debug=False):
    api_key_name = 'nzbyfwhwaoanttzje'
    if data and api_key_name in data and isinstance(
            data[api_key_name], list) and len(data[api_key_name]) > 1:
        return data[api_key_name][1].get('row', [])
    return []


# --- Speaker and Party Data Handling ---
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_speaker_details(self, speaker_name):
    try:
        if not settings.ASSEMBLY_API_KEY:
            logger.error("ASSEMBLY_API_KEY not configured.")
            return None
        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "NAAS_NM": speaker_name,
            "Type": "json",
            "pSize": 5
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
            member_data = data['ALLNAMEMBER'][1].get('row', [None])[0]
            if member_data:
                speaker, created = Speaker.objects.update_or_create(
                    naas_cd=member_data.get('NAAS_CD'),
                    defaults={
                        'naas_nm': member_data.get('NAAS_NM', speaker_name),
                        'plpt_nm': member_data.get('PLPT_NM', '정당정보없음'),
                        'naas_pic': member_data.get('NAAS_PIC', '')
                    })
                logger.info(
                    f"{'Created' if created else 'Updated'} speaker: {speaker_name}"
                )
                return speaker
        logger.warning(f"No member data for: {speaker_name}.")
        return None
    except Exception as e:
        logger.error(f"Error fetching speaker details for {speaker_name}: {e}")
        return None


@with_db_retry()
def _create_fallback_speaker(speaker_name_cleaned):
    temp_naas_cd = f"TEMP_{speaker_name_cleaned.replace(' ', '_')}_{int(time.time())}"
    speaker, created = Speaker.objects.get_or_create(
        naas_nm=speaker_name_cleaned,
        defaults={
            'naas_cd': temp_naas_cd,
            'plpt_nm': '정보없음'
        })
    if created:
        logger.info(f"Created fallback speaker: '{speaker_name_cleaned}'")
    return speaker


def get_or_create_speaker(speaker_name_raw, debug=False):
    speaker_name_cleaned = (speaker_name_raw or "").strip()
    if not speaker_name_cleaned:
        logger.warning("Empty speaker name.")
        return None
    try:
        speaker_obj = Speaker.objects.filter(
            naas_nm=speaker_name_cleaned).first()
        if speaker_obj: return speaker_obj
    except Exception as e:
        logger.error(f"DB error finding speaker '{speaker_name_cleaned}': {e}")
    if not debug:
        try:
            # Using .get() makes this synchronous, which is intended here.
            speaker_from_api = fetch_speaker_details.delay(
                speaker_name_cleaned).get(timeout=30)
            if speaker_from_api: return speaker_from_api
        except Exception as e:
            logger.error(
                f"API task for speaker '{speaker_name_cleaned}' failed: {e}")
    try:
        return _create_fallback_speaker(speaker_name_cleaned)
    except Exception as e:
        logger.error(
            f"CRITICAL: Failed to create fallback speaker '{speaker_name_cleaned}': {e}"
        )
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_party_membership_data(self, force=False, debug=False):
    logger.info(
        f"🏛️ Fetching all party membership data (force={force}, debug={debug})"
    )
    try:
        if not settings.ASSEMBLY_API_KEY:
            logger.error("ASSEMBLY_API_KEY not configured.")
            return
        url, all_members, page, page_size = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER", [], 1, 300
        while page <= 10:
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": page,
                "pSize": page_size
            }
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            members_on_page = response.json().get('ALLNAMEMBER',
                                                  [{}, {}])[1].get('row', [])
            if not members_on_page:
                logger.info(f"No members on page {page}, ending.")
                break
            all_members.extend(members_on_page)
            if len(members_on_page) < page_size: break
            page += 1
            time.sleep(1)
        if not all_members:
            logger.info("No membership data from API.")
            return
        logger.info(f"✅ Found {len(all_members)} total members.")
        for member_data in all_members:
            try:
                party_name = member_data.get('PLPT_NM', '').strip()
                speaker, _ = Speaker.objects.update_or_create(
                    naas_cd=member_data.get('NAAS_CD'),
                    defaults={
                        'naas_nm': member_data.get('NAAS_NM', '').strip(),
                        'plpt_nm': party_name or '정당정보없음',
                        'naas_pic': member_data.get('NAAS_PIC', '')
                    })
                if party_name and party_name != '정당정보없음':
                    party, _ = Party.objects.get_or_create(name=party_name)
                    if not speaker.current_party:
                        speaker.current_party = party
                        speaker.save()
            except Exception as e:
                logger.error(
                    f"Error processing member data: {e} - Item: {member_data}")
        logger.info(f"🎉 Processed {len(all_members)} membership records.")
    except RequestException as re_exc:
        logger.error(f"Request error: {re_exc}")
        self.retry(exc=re_exc)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        self.retry(exc=e)


# --- Core Data Fetching Pipeline ---
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_latest_sessions(self, force=False, debug=False):
    logger.info(f"🔍 Starting session fetch (force={force})")
    url, DAE_NUM = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje", "22"
    dates = [datetime.now().strftime('%Y-%m')]
    if not force:
        dates.append((datetime.now() - timedelta(days=30)).strftime('%Y-%m'))
    else:
        dates.extend([
            (datetime.now() - timedelta(days=i * 30)).strftime('%Y-%m')
            for i in range(1, 24)
        ])
    for date_str in sorted(list(set(dates)), reverse=True):
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "DAE_NUM": DAE_NUM,
            "CONF_DATE": date_str,
            "pSize": 500
        }
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            sessions_data = extract_sessions_from_response(response.json())
            if sessions_data:
                process_sessions_data(sessions_data, force=force, debug=debug)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"⚠️ Error for {date_str}: {e}")


@with_db_retry()
def process_sessions_data(sessions_data, force=False, debug=False):
    for item in sessions_data:
        confer_num = item.get('CONFER_NUM')
        if not confer_num: continue
        defaults = {
            'title': item.get('TITLE', '제목 없음'),
            'down_url': item.get('PDF_LINK_URL', '')
        }
        session_obj, created = Session.objects.update_or_create(
            conf_id=confer_num, defaults=defaults)
        if created or force:
            logger.info(
                f"{'✨ Created' if created else '🔄 Force-processing'} session: {confer_num}"
            )
            fetch_session_bills.delay(session_id=confer_num,
                                      force=force,
                                      debug=debug)
            if session_obj.down_url:
                process_session_pdf.delay(session_id=confer_num,
                                          force=force,
                                          debug=debug)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_session_bills(self, session_id, force=False, debug=False):
    url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "Type": "json",
        "CONF_ID": format_conf_id(session_id),
        "pSize": 500
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        bills_data = response.json().get('VCONFBILLLIST',
                                         [{}, {}])[1].get('row', [])
        if not bills_data:
            logger.info(f"ℹ️ No bills for session {session_id}.")
            return
        session_obj = Session.objects.get(conf_id=session_id)
        for item in bills_data:
            bill_id = item.get('BILL_ID')
            if not bill_id: continue
            _, created = Bill.objects.update_or_create(
                bill_id=bill_id,
                defaults={
                    'session': session_obj,
                    'bill_nm': item.get('BILL_NM', ''),
                    'proposer': item.get('PROPOSER', '정보 없음')
                })
            if created or force:
                fetch_bill_detail_info.delay(bill_id, force=force, debug=debug)
    except Session.DoesNotExist:
        logger.error(f"❌ Session {session_id} not found.")
    except Exception as e:
        logger.error(f"❌ Error fetching bills for {session_id}: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_bill_detail_info(self, bill_id, force=False, debug=False):
    url = "https://open.assembly.go.kr/portal/openapi/BILLINFODETAIL"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "BILL_ID": bill_id,
        "Type": "json"
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        detail_data = response.json().get('BILLINFODETAIL',
                                          [{}, {}])[1].get('row', [None])[0]
        if not detail_data: return
        bill = Bill.objects.get(bill_id=bill_id)
        kind = detail_data.get('PPSR_KIND', '').strip()
        name = detail_data.get('PPSR', '').strip()
        bill.proposer = f"{name} ({kind})" if kind and name else name or "정보 없음"
        bill.link_url = f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}"
        bill.save()
        logger.info(f"✅ Updated bill {bill_id} proposer: {bill.proposer}")
        if ENABLE_VOTING_DATA_COLLECTION:
            fetch_voting_data_for_bill.delay(bill_id, force=force, debug=debug)
    except Bill.DoesNotExist:
        logger.error(f"Bill {bill_id} not found.")
    except Exception as e:
        logger.error(f"❌ Error fetching detail for {bill_id}: {e}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_voting_data_for_bill(self, bill_id, force=False, debug=False):
    url = "https://open.assembly.go.kr/portal/openapi/nojepdqqaweusdfbi"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "AGE": "22",
        "BILL_ID": bill_id,
        "Type": "json",
        "pSize": 300
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        voting_data = response.json().get('nojepdqqaweusdfbi',
                                          [{}, {}])[1].get('row', [])
        if not voting_data:
            logger.info(f"No voting data for bill {bill_id}")
            return
        bill = Bill.objects.get(bill_id=bill_id)
        records = []
        for item in voting_data:
            name = item.get('HG_NM', '').strip()
            if not name: continue
            speaker = get_or_create_speaker(name, debug)
            if speaker:
                records.append(
                    VotingRecord(bill=bill,
                                 speaker=speaker,
                                 vote_result=item.get('RESULT_VOTE_MOD',
                                                      '').strip(),
                                 session=bill.session))
        if records:
            VotingRecord.objects.bulk_create(records, ignore_conflicts=True)
            logger.info(
                f"✨ Bulk created {len(records)} voting records for bill {bill_id}."
            )
    except Bill.DoesNotExist:
        logger.error(f"Bill {bill_id} not found.")
    except Exception as e:
        logger.error(f"❌ Error fetching voting data for {bill_id}: {e}")
        self.retry(exc=e)


# --- AI Processing Core Logic ---
def _run_ai_processing_on_text(session_obj,
                               cleaned_text,
                               bill_names_list_from_api,
                               debug=False):
    """Internal function with the core AI processing logic."""
    logger.info(
        f"Running AI processing for session {session_obj.conf_id} on {len(cleaned_text)} chars."
    )
    known_bills_str = "\n".join(f"- {name}"
                                for name in bill_names_list_from_api) or "N/A"
    master_prompt = f"""You are an elite legislative data processor. Your task is to read a parliamentary transcript and convert it into a structured JSON object. Adhere to the format with absolute precision.
    CONTEXT:
    Known Bills for this Session:
    {known_bills_str}
    MISSION:
    1. Parse the entire transcript.
    2. Identify every distinct bill or topic discussed.
    3. For each topic, provide a concise policy analysis.
    4. Within each topic, extract every individual speech, typically marked by "◯".
    REQUIRED JSON OUTPUT FORMAT:
    {{
      "discussion_segments": [
        {{
          "bill_name": "Full and exact name of the Bill or Topic", "is_newly_discovered": boolean,
          "policy_analysis": {{ "main_category": "e.g., Economy", "sub_categories": ["e.g., Tax Reform"], "keywords": ["e.g., income tax"] }},
          "statements": [
            {{ "speaker_name": "Full name of speaker, titles removed.", "text": "Verbatim text of the speech." }}
          ]
        }}
      ]
    }}
    """
    response = GEMINI.execute_api_call(contents=[master_prompt, cleaned_text])
    if not response or not hasattr(response, 'text'):
        raise ValueError(
            f"Master LLM call failed for session {session_obj.conf_id}.")
    _process_llm_response_data(session_obj, response.text, debug)


# --- Master AI Orchestrator and Wrappers ---
@shared_task(bind=True, max_retries=3, default_retry_delay=60 * 5)
def process_session_pdf(self, session_id, force=False, debug=False):
    """Celery Task: Fetches PDF, extracts text, and runs AI processing."""
    logger.info(
        f"Initiating AI processing pipeline for session {session_id}...")
    try:
        session_obj = Session.objects.get(conf_id=session_id)
        if not session_obj.down_url:
            logger.info(f"No PDF URL for session {session_id}. Skipping.")
            return
        full_text = _download_and_extract_pdf_text(session_obj.down_url)
        if not full_text:
            raise ValueError(
                f"Failed to extract text from PDF for {session_id}.")

        cleaned_text = clean_pdf_text(full_text)
        bill_names_list_from_api = get_session_bill_names(session_id)

        _run_ai_processing_on_text(session_obj, cleaned_text,
                                   bill_names_list_from_api, debug)
        logger.info(f"Successfully processed session {session_id}.")
    except Session.DoesNotExist:
        logger.error(f"Session {session_id} not found.")
        return
    except Exception as e:
        logger.critical(f"CRITICAL: AI pipeline for {session_id} failed: {e}",
                        exc_info=True)
        self.retry(exc=e)


def process_session_pdf_text(full_text,
                             session_id,
                             session_obj,
                             bills_context_str,
                             bill_names_list_from_api,
                             debug=False):
    """Directly callable function for processing pre-extracted PDF text. (For management command)"""
    logger.info(f"Directly processing PDF text for session {session_id}...")
    try:
        cleaned_text = clean_pdf_text(full_text)
        _run_ai_processing_on_text(session_obj, cleaned_text,
                                   bill_names_list_from_api, debug)
        logger.info(
            f"Direct text processing complete for session {session_id}.")
    except Exception as e:
        logger.error(
            f"Error in direct text processing for session {session_id}: {e}",
            exc_info=True)
        raise


@with_db_retry()
def _process_llm_response_data(session_obj, raw_json_text, debug):
    try:
        if raw_json_text.strip().startswith("```json"):
            raw_json_text = raw_json_text.strip()[7:-4].strip()
        data = json.loads(raw_json_text)
        discussion_segments = data.get("discussion_segments", [])
        if not discussion_segments:
            logger.warning(f"LLM found no segments for {session_obj.conf_id}.")
            return
        logger.info(
            f"Processing {len(discussion_segments)} segments from LLM.")
        for segment in discussion_segments:
            bill_name = segment.get("bill_name")
            if not bill_name: continue
            bill_obj, _ = Bill.objects.get_or_create(
                bill_nm=bill_name,
                session=session_obj,
                defaults={
                    'bill_id': f"LLM_{session_obj.conf_id}_{hash(bill_name)}"
                })
            update_bill_policy_data(bill_obj,
                                    segment.get("policy_analysis", {}))
            statements_to_create = []
            for stmt_data in segment.get("statements", []):
                speaker_name, text = stmt_data.get(
                    "speaker_name"), stmt_data.get("text")
                if speaker_name and text:
                    speaker = get_or_create_speaker(speaker_name, debug)
                    if speaker:
                        statements_to_create.append(
                            Statement(session=session_obj,
                                      bill=bill_obj,
                                      speaker=speaker,
                                      content=text))
            if statements_to_create:
                Statement.objects.bulk_create(statements_to_create,
                                              ignore_conflicts=True)
        logger.info(f"✅ Saved statements for session {session_obj.conf_id}.")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            f"Failed to parse LLM JSON for {session_obj.conf_id}: {e}\nRaw Text: {raw_json_text[:500]}"
        )
        raise ValueError("LLM response not valid JSON.") from e


# --- PDF and Text Processing Helpers ---
def _download_and_extract_pdf_text(pdf_url: str) -> str:
    logger.info(f"Downloading PDF from {pdf_url}")
    try:
        response = requests.get(pdf_url, timeout=120)
        response.raise_for_status()
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages
                             if page.extract_text())
    except Exception as e:
        logger.error(f"Failed PDF processing for {pdf_url}: {e}",
                     exc_info=True)
    return ""


def clean_pdf_text(text: str) -> str:
    if not text: return ""
    start_match = re.search(r'\(\d{1,2}시\s*\d{1,2}분\s+개의\)', text)
    if not start_match:
        logger.warning("No meeting start marker found.")
        return text
    start_pos = start_match.start()
    end_patterns = [
        r'\(\d{1,2}시\s*\d{1,2}분\s+산회\)',
        r'\(\d{1,2}시\s*\d{1,2}분\s+폐회\)',
    ]
    end_pos = len(text)
    for pattern in end_patterns:
        end_match = re.search(pattern, text[start_pos:])
        if end_match:
            end_pos = start_pos + end_match.end()
            break
    block = text[start_pos:end_pos]
    header = re.compile(r'^제\d+회-제\d+차\s*\(.+?\)\s*\d+\s*$')
    report_note = re.compile(r'\(보고사항은\s*끝에\s*실음\)')
    lines = [report_note.sub('', line).strip() for line in block.split('\n')]
    final_text = "\n".join(line for line in lines
                           if line and not header.match(line))
    return re.sub(r'\n{2,}', '\n', final_text)


@with_db_retry()
def get_session_bill_names(session_id):
    try:
        return list(
            Bill.objects.filter(session__conf_id=session_id).values_list(
                'bill_nm', flat=True))
    except Exception as e:
        logger.error(f"Failed to get bill names for {session_id}: {e}")
        return []


@with_db_retry()
def update_bill_policy_data(bill_obj, policy_data):
    if not policy_data or not isinstance(policy_data, dict): return
    main_cat, sub_cats, keywords = policy_data.get(
        'main_category',
        ''), policy_data.get('sub_categories',
                             []), policy_data.get('keywords', [])
    bill_obj.policy_keywords = ', '.join(keywords)
    bill_obj.save()
    if main_cat:
        try:
            cat_obj, _ = Category.objects.get_or_create(name=main_cat)
            BillCategoryMapping.objects.update_or_create(bill=bill_obj,
                                                         category=cat_obj)
            for sub_name in sub_cats:
                sub_obj, _ = Subcategory.objects.get_or_create(
                    name=sub_name, category=cat_obj)
                BillSubcategoryMapping.objects.update_or_create(
                    bill=bill_obj, subcategory=sub_obj)
        except Exception as e:
            logger.error(
                f"Error creating category mappings for bill {bill_obj.id}: {e}"
            )
