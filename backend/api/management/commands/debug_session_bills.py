
from django.core.management.base import BaseCommand
from api.models import Session, Bill
from api.tasks import fetch_session_details, fetch_session_bills
import requests
from django.conf import settings
import json


class Command(BaseCommand):
    help = 'Debug bill fetching issues for a specific session'

    def add_arguments(self, parser):
        parser.add_argument('session_id', type=str, help='Session ID to debug')
        parser.add_argument('--fix', action='store_true', help='Attempt to fix by fetching bills')
        parser.add_argument('--api-debug', action='store_true', help='Show raw API responses')

    def handle(self, *args, **options):
        session_id = options['session_id']
        fix = options['fix']
        api_debug = options['api_debug']
        
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'🔍 Debugging session: {session_id}')
            self.stdout.write(f'📄 Session: {session.title or session.conf_knd}')
            self.stdout.write(f'📅 Date: {session.conf_dt}')
            self.stdout.write(f'🏛️ Committee: {session.cmit_nm}')
            self.stdout.write(f'🔗 PDF URL: {session.down_url}')
            
            # Check existing bills
            bills = Bill.objects.filter(session=session)
            self.stdout.write(f'📊 Bills found: {bills.count()}')
            
            if bills.exists():
                self.stdout.write('📋 Existing bills:')
                for bill in bills:
                    self.stdout.write(f'  - {bill.bill_nm} (ID: {bill.bill_id})')
            else:
                self.stdout.write('⚠️ No bills found for this session')
                
                if api_debug:
                    self.debug_api_call(session_id)
                
                if fix:
                    self.stdout.write('🔧 Attempting to fetch bills...')
                    
                    # First fetch session details (which triggers bill fetching)
                    fetch_session_details(session_id=session_id, force=True, debug=False)
                    
                    # Then explicitly fetch bills
                    fetch_session_bills(session_id=session_id, force=True, debug=False)
                    
                    # Check again
                    bills_after = Bill.objects.filter(session=session)
                    self.stdout.write(f'📊 Bills found after fetch: {bills_after.count()}')
                    
                    if bills_after.exists():
                        self.stdout.write('✅ Bills successfully fetched:')
                        for bill in bills_after:
                            self.stdout.write(f'  - {bill.bill_nm} (ID: {bill.bill_id})')
                    else:
                        self.stdout.write('❌ Still no bills found. This session may not have associated bills in the API.')
                        
                        # Analyze the session type
                        self.analyze_session_type(session)
                else:
                    self.stdout.write('💡 Use --fix to attempt fetching bills from the API')
                    self.stdout.write('💡 Use --api-debug to see raw API responses')
            
        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found in database'))

    def debug_api_call(self, session_id):
        """Debug the actual API call to VCONFBILLLIST"""
        self.stdout.write('\n🔍 Testing direct API call to VCONFBILLLIST...')
        
        if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
            return
        
        # Format session ID properly (6 digits)
        formatted_conf_id = str(session_id).zfill(6)
        
        url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json",
            "CONF_ID": formatted_conf_id,
            "pSize": 500
        }
        
        self.stdout.write(f'📡 API URL: {url}')
        self.stdout.write(f'📋 Parameters: {params}')
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            self.stdout.write(f'✅ API Response Status: {response.status_code}')
            self.stdout.write(f'📄 Raw API Response:')
            self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Analyze the response
            api_key_name = 'VCONFBILLLIST'
            if data and api_key_name in data and isinstance(data[api_key_name], list):
                if len(data[api_key_name]) > 1 and isinstance(data[api_key_name][1], dict):
                    bills_data = data[api_key_name][1].get('row', [])
                    self.stdout.write(f'📊 Bills found in API response: {len(bills_data)}')
                elif len(data[api_key_name]) > 0 and isinstance(data[api_key_name][0], dict):
                    head_info = data[api_key_name][0].get('head')
                    if head_info:
                        result_info = head_info[0].get('RESULT', {})
                        result_code = result_info.get('CODE', '')
                        result_message = result_info.get('MESSAGE', '')
                        self.stdout.write(f'📋 API Result Code: {result_code}')
                        self.stdout.write(f'📋 API Result Message: {result_message}')
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'❌ API Request failed: {e}'))
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'❌ JSON parsing failed: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Unexpected error: {e}'))

    def analyze_session_type(self, session):
        """Analyze why this session might not have bills"""
        self.stdout.write('\n🔍 Session Analysis:')
        
        # Check if it's a general assembly vs committee meeting
        if '본회의' in session.cmit_nm or '국회본회의' in session.cmit_nm:
            self.stdout.write('🏛️ This is a general assembly meeting (본회의)')
            self.stdout.write('  - General assemblies may not have specific bills listed in VCONFBILLLIST')
            self.stdout.write('  - They might discuss multiple bills or procedural matters')
        elif '위원회' in session.cmit_nm:
            self.stdout.write(f'🏛️ This is a committee meeting: {session.cmit_nm}')
            self.stdout.write('  - Committee meetings usually have associated bills')
            self.stdout.write('  - This might be a procedural or general discussion meeting')
        else:
            self.stdout.write(f'🏛️ Session type: {session.cmit_nm}')
        
        # Check the session title for clues
        if session.title:
            if '보고' in session.title:
                self.stdout.write('📋 Session appears to be a reporting session (보고)')
            elif '질의' in session.title:
                self.stdout.write('📋 Session appears to be a Q&A session (질의)')
            elif '심사' in session.title:
                self.stdout.write('📋 Session appears to be a review session (심사)')
            elif '의결' in session.title:
                self.stdout.write('📋 Session appears to be a decision session (의결)')
        
        self.stdout.write('\n🔍 Possible reasons for no bills:')
        self.stdout.write('  1. Procedural or administrative meeting')
        self.stdout.write('  2. General discussion without specific bills')
        self.stdout.write('  3. Reporting session (보고사항)')
        self.stdout.write('  4. Bills discussed but not formally listed in API')
        self.stdout.write('  5. API data inconsistency or delay')
        
        # Suggest alternatives
        self.stdout.write('\n💡 Suggestions:')
        self.stdout.write('  - Check if PDF processing can extract bill information from transcript')
        self.stdout.write('  - Try processing the PDF to see if bills are mentioned in the content')
        self.stdout.write(f'  - Run: python manage.py test_llm_with_pdf --session-id {session.conf_id}')
