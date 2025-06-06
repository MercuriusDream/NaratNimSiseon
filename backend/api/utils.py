import logging
import requests
from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Session, Bill, Speaker, Statement

logger = logging.getLogger(__name__)


def api_action_wrapper(default_error_message="오류가 발생했습니다.",
                       log_prefix="Error"):

    def decorator(func):

        @wraps(func)
        def wrapper(*args, **kwargs):
            # self is args[0] (the viewset instance)
            # request is args[1]
            # pk (or other path params) are in kwargs
            viewset_instance = args[0]
            action_name = func.__name__
            # Construct a more specific log prefix if possible, e.g., using pk
            item_pk = kwargs.get('pk', 'N/A')
            full_log_prefix = f"{log_prefix} in {viewset_instance.__class__.__name__}.{action_name} (pk={item_pk})"

            try:
                return func(*args, **kwargs)
            except Http404 as e:
                logger.warning(f"{full_log_prefix}: Resource not found - {e}")
                return Response(
                    {
                        'status': 'error',
                        'message': str(e) if str(e) else
                        "리소스를 찾을 수 없습니다."  # Provide a default if str(e) is empty
                    },
                    status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"{full_log_prefix}: {e}")
                return Response(
                    {
                        'status': 'error',
                        'message': default_error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return wrapper

    return decorator


def format_conf_id(session_id):
    """Format session ID to the required 6-digit zero-filled format for API calls"""
    if session_id is None:
        return None
    return str(session_id).strip().zfill(6)


class DataCollector:
    """Utility class for collecting data from National Assembly API"""

    BASE_URL = "https://open.assembly.go.kr/portal/openapi"

    def __init__(self, api_key="sample"):
        self.api_key = api_key

    def fetch_sessions(self, num_records=100, force=False):
        """Fetch session data from API"""
        try:
            url = f"{self.BASE_URL}/nwvrqwxyaytdsfvhu"
            params = {
                'Key': self.api_key,
                'Type': 'json',
                'pIndex': 1,
                'pSize': num_records
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'nwvrqwxyaytdsfvhu' in data and data['nwvrqwxyaytdsfvhu'][0][
                    'head'][0]['RESULT']['CODE'] == 'INFO-000':
                sessions_data = data['nwvrqwxyaytdsfvhu'][1]['row']
                logger.info(
                    f"Successfully fetched {len(sessions_data)} sessions")
                return sessions_data
            else:
                logger.warning("No session data returned from API")
                return []

        except Exception as e:
            logger.error(f"Error fetching sessions: {e}")
            return []

    def fetch_bills(self, num_records=100, session_id=None):
        """Fetch bill data from API"""
        try:
            url = f"{self.BASE_URL}/VCONFBILLLIST"
            params = {
                'KEY': self.api_key,
                'Type': 'json',
                'pIndex': 1,
                'pSize': num_records
            }

            if session_id:
                params['CONF_ID'] = str(session_id).zfill(6)

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'VCONFBILLLIST' in data and data['VCONFBILLLIST'][0]['head'][0][
                    'RESULT']['CODE'] == 'INFO-000':
                bills_data = data['VCONFBILLLIST'][1]['row']
                logger.info(f"Successfully fetched {len(bills_data)} bills")
                return bills_data
            else:
                logger.warning("No bill data returned from API")
                return []

        except Exception as e:
            logger.error(f"Error fetching bills: {e}")
            return []

    def save_session_data(self, sessions_data, force=False):
        """Save session data to database"""
        saved_count = 0

        for session_data in sessions_data:
            try:
                session_id = session_data.get('SESS_ID')
                if not session_id:
                    continue

                # Check if session already exists
                if not force and Session.objects.filter(
                        sess_id=session_id).exists():
                    continue

                # Create or update session
                session, created = Session.objects.update_or_create(
                    sess_id=session_id,
                    defaults={
                        'sess_nm': session_data.get('SESS_NM', ''),
                        'conf_dt':
                        self._parse_date(session_data.get('CONF_DT')),
                        'st_tm': session_data.get('ST_TM', ''),
                        'ed_tm': session_data.get('ED_TM', ''),
                        'down_url': session_data.get('DOWN_URL', ''),
                        'created_at': timezone.now()
                    })

                if created or force:
                    saved_count += 1

            except Exception as e:
                logger.error(
                    f"Error saving session {session_data.get('SESS_ID')}: {e}")
                continue

        logger.info(f"Saved {saved_count} sessions to database")
        return saved_count

    def save_bill_data(self, bills_data):
        """Save bill data to database"""
        saved_count = 0

        for bill_data in bills_data:
            try:
                bill_id = bill_data.get('BILL_ID')
                if not bill_id:
                    continue

                # Create or update bill
                bill, created = Bill.objects.update_or_create(
                    bill_id=bill_id,
                    defaults={
                        'bill_nm': bill_data.get('BILL_NM', ''),
                        'bill_kind_cd': bill_data.get('BILL_KIND_CD', ''),
                        'propose_dt':
                        self._parse_date(bill_data.get('PROPOSE_DT')),
                        'committee': bill_data.get('COMMITTEE', ''),
                        'proposer': bill_data.get('PROPOSER', ''),
                        'summary': bill_data.get('SUMMARY', ''),
                        'created_at': timezone.now()
                    })

                if created:
                    saved_count += 1

            except Exception as e:
                logger.error(
                    f"Error saving bill {bill_data.get('BILL_ID')}: {e}")
                continue

        logger.info(f"Saved {saved_count} bills to database")
        return saved_count

    def _parse_date(self, date_str):
        """Parse date string to datetime object"""
        if not date_str:
            return None

        try:
            # Handle different date formats
            if len(date_str) == 8:  # YYYYMMDD
                return datetime.strptime(date_str, '%Y%m%d').date()
            elif len(date_str) == 10:  # YYYY-MM-DD
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                return None
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")
            return None
