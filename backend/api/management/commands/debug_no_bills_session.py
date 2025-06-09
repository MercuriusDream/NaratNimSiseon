
<old_str>from django.core.management.base import BaseCommand
from api.models import Session, Bill
from api.tasks import fetch_session_bills, fetch_session_details, is_celery_available
import requests
import json

class Command(BaseCommand):
    help = 'Debug a session that has no bills and attempt to fetch them'

    def add_arguments(self, parser):
        parser.add_argument(
            'session_id',
            type=str,
            help='Session ID to debug and fix',
        )
        parser.add_argument(
            '--force-refetch',
            action='store_true',
            help='Force refetch bills even if some exist',
        )
        parser.add_argument(
            '--api-debug',
            action='store_true',
            help='Show detailed API responses',
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        force_refetch = options.get('force_refetch', False)
        api_debug = options.get('api_debug', False)

        self.stdout.write(f'🔍 Debugging session: {session_id}')

        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'📄 Session: {session.title or session.conf_knd}')
            self.stdout.write(f'📅 Date: {session.conf_dt}')
            self.stdout.write(f'🏛️ Committee: {session.cmit_nm}')
            self.stdout.write(f'🔗 PDF URL: {session.down_url}')

            # Check current bill count
            current_bills = Bill.objects.filter(session=session)
            self.stdout.write(f'📊 Current bills in DB: {current_bills.count()}')

            if current_bills.exists() and not force_refetch:
                self.stdout.write('📋 Existing bills:')
                for i, bill in enumerate(current_bills.order_by('-id')[:5], 1):
                    self.stdout.write(f'  - {i}. {bill.bill_nm} (ID: {bill.bill_id})')
                if current_bills.count() > 5:
                    self.stdout.write(f'  ... and {current_bills.count() - 5} more')
                self.stdout.write('\nℹ️ Use --force-refetch to fetch bills again')
                return

            # Check VCONFBILLLIST API directly
            self.stdout.write('\n🔍 Checking VCONFBILLLIST API directly...')
            
            from django.conf import settings
            if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
                self.stdout.write(self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
                return

            # Format session ID for API call
            formatted_conf_id = str(session_id).replace('N', '').strip().zfill(6)
            url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "CONF_ID": formatted_conf_id,
                "pSize": 500
            }

            self.stdout.write(f'🔗 API URL: {url}')
            self.stdout.write(f'📋 Parameters: CONF_ID={formatted_conf_id}')

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if api_debug:
                    self.stdout.write(f'🐛 Full API Response:')
                    self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))

                # Parse bills data
                bills_data = []
                api_key_name = 'VCONFBILLLIST'
                
                if data and api_key_name in data and isinstance(data[api_key_name], list):
                    if len(data[api_key_name]) > 1 and isinstance(data[api_key_name][1], dict):
                        bills_data = data[api_key_name][1].get('row', [])
                    elif len(data[api_key_name]) > 0 and isinstance(data[api_key_name][0], dict):
                        head_info = data[api_key_name][0].get('head')
                        if head_info and head_info[0].get('RESULT', {}).get('CODE', '').startswith("INFO-200"):
                            self.stdout.write("ℹ️ API indicates no bill data available (INFO-200)")
                        elif 'row' in data[api_key_name][0]:
                            bills_data = data[api_key_name][0].get('row', [])

                if bills_data:
                    self.stdout.write(f'✅ Found {len(bills_data)} bills in API response:')
                    for i, bill in enumerate(bills_data, 1):
                        bill_name = bill.get('BILL_NM', 'Unknown')
                        bill_id = bill.get('BILL_ID', 'Unknown')
                        proposer = bill.get('PROPOSER', 'Unknown')
                        self.stdout.write(f'  {i}. {bill_name}')
                        self.stdout.write(f'     - ID: {bill_id}')
                        self.stdout.write(f'     - Proposer: {proposer}')

                    # Trigger bill fetch
                    self.stdout.write('\n🚀 Triggering bill fetch for this session...')
                    if is_celery_available():
                        fetch_session_bills.delay(session_id=session_id, force=True, debug=False)
                        self.stdout.write('✅ Bill fetch task queued with Celery')
                    else:
                        fetch_session_bills(session_id=session_id, force=True, debug=False)
                        self.stdout.write('✅ Bill fetch completed synchronously')

                    # Check results
                    updated_bills = Bill.objects.filter(session=session)
                    self.stdout.write(f'📊 Bills after fetch: {updated_bills.count()}')

                    if updated_bills.exists():
                        self.stdout.write('🎉 Bills successfully fetched! You can now reprocess the PDF.')
                        self.stdout.write('\n💡 To reprocess the PDF with bills:')
                        self.stdout.write(f'   python manage.py test_llm_with_pdf --session-id {session_id} --force')
                else:
                    self.stdout.write('❌ No bills found in API response')
                    self.stdout.write('\n🔍 Possible reasons:')
                    self.stdout.write('  1. This session has no associated bills (administrative session)')
                    self.stdout.write('  2. Bills not yet added to the API system')
                    self.stdout.write('  3. Session ID format issue')
                    self.stdout.write('  4. API timing/sync issue')

                    # Check if we should try session details instead
                    self.stdout.write('\n🔄 Trying to fetch session details first...')
                    if is_celery_available():
                        fetch_session_details.delay(session_id=session_id, force=True, debug=False)
                        self.stdout.write('✅ Session details fetch queued')
                    else:
                        fetch_session_details(session_id=session_id, force=True, debug=False)
                        self.stdout.write('✅ Session details fetch completed')

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f'❌ API request failed: {e}'))
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f'❌ JSON parsing failed: {e}'))

        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found in database'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))</old_str>
<new_str>from django.core.management.base import BaseCommand
from api.models import Session, Bill, Statement
from api.tasks import fetch_session_bills, fetch_session_details, is_celery_available, get_session_bill_names
import requests
import json
import traceback

class Command(BaseCommand):
    help = 'Debug a session that has no bills and show detailed error information'

    def add_arguments(self, parser):
        parser.add_argument(
            'session_id',
            type=str,
            help='Session ID to debug and fix',
        )
        parser.add_argument(
            '--force-refetch',
            action='store_true',
            help='Force refetch bills even if some exist',
        )
        parser.add_argument(
            '--api-debug',
            action='store_true',
            help='Show detailed API responses',
        )
        parser.add_argument(
            '--show-statements',
            action='store_true',
            help='Show existing statements for this session',
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        force_refetch = options.get('force_refetch', False)
        api_debug = options.get('api_debug', False)
        show_statements = options.get('show_statements', False)

        self.stdout.write(self.style.SUCCESS(f'🔍 Debugging session: {session_id}'))

        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'📄 Session: {session.title or session.conf_knd}')
            self.stdout.write(f'📅 Date: {session.conf_dt}')
            self.stdout.write(f'🏛️ Committee: {session.cmit_nm}')
            self.stdout.write(f'🔗 PDF URL: {session.down_url}')

            # Check current bill count
            current_bills = Bill.objects.filter(session=session)
            self.stdout.write(f'📊 Current bills in DB: {current_bills.count()}')

            # Check statements
            current_statements = Statement.objects.filter(session=session)
            self.stdout.write(f'💬 Current statements in DB: {current_statements.count()}')

            if current_bills.exists() and not force_refetch:
                self.stdout.write('📋 Existing bills:')
                for i, bill in enumerate(current_bills.order_by('-id')[:5], 1):
                    self.stdout.write(f'  - {i}. {bill.bill_nm} (ID: {bill.bill_id})')
                    if bill.proposer:
                        self.stdout.write(f'     Proposer: {bill.proposer}')
                if current_bills.count() > 5:
                    self.stdout.write(f'  ... and {current_bills.count() - 5} more')
                
                if not force_refetch:
                    self.stdout.write('\nℹ️ Use --force-refetch to fetch bills again')
                    
                    if show_statements and current_statements.exists():
                        self.stdout.write('\n💬 Sample statements:')
                        for i, stmt in enumerate(current_statements[:3], 1):
                            self.stdout.write(f'  {i}. {stmt.speaker.naas_nm}: {stmt.text[:100]}...')

            # Test get_session_bill_names function
            self.stdout.write('\n🔍 Testing get_session_bill_names function...')
            try:
                bill_names = get_session_bill_names(session_id)
                if bill_names:
                    self.stdout.write(f'✅ Found {len(bill_names)} bill names from get_session_bill_names:')
                    for name in bill_names[:5]:
                        self.stdout.write(f'  - {name}')
                    if len(bill_names) > 5:
                        self.stdout.write(f'  ... and {len(bill_names) - 5} more')
                else:
                    self.stdout.write(self.style.WARNING('⚠️ get_session_bill_names returned empty list'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error in get_session_bill_names: {e}'))
                self.stdout.write(f'Traceback: {traceback.format_exc()}')

            # Check VCONFBILLLIST API directly
            self.stdout.write('\n🔍 Checking VCONFBILLLIST API directly...')
            
            from django.conf import settings
            if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
                self.stdout.write(self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
                return

            # Format session ID for API call
            formatted_conf_id = str(session_id).replace('N', '').strip().zfill(6)
            url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "CONF_ID": formatted_conf_id,
                "pSize": 500
            }

            self.stdout.write(f'🔗 API URL: {url}')
            self.stdout.write(f'📋 Parameters: CONF_ID={formatted_conf_id}')

            try:
                response = requests.get(url, params=params, timeout=30)
                self.stdout.write(f'📡 HTTP Status: {response.status_code}')
                response.raise_for_status()
                data = response.json()

                if api_debug:
                    self.stdout.write(f'🐛 Full API Response:')
                    self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))

                # Parse bills data with detailed error information
                bills_data = []
                api_key_name = 'VCONFBILLLIST'
                
                self.stdout.write(f'\n🔍 Parsing API response structure...')
                
                if not data:
                    self.stdout.write(self.style.ERROR('❌ API returned empty response'))
                elif api_key_name not in data:
                    self.stdout.write(self.style.ERROR(f'❌ API response missing "{api_key_name}" key'))
                    self.stdout.write(f'Available keys: {list(data.keys())}')
                elif not isinstance(data[api_key_name], list):
                    self.stdout.write(self.style.ERROR(f'❌ API response "{api_key_name}" is not a list'))
                    self.stdout.write(f'Type: {type(data[api_key_name])}')
                else:
                    self.stdout.write(f'✅ API response structure is valid')
                    self.stdout.write(f'   - {api_key_name} array length: {len(data[api_key_name])}')
                    
                    if len(data[api_key_name]) > 1 and isinstance(data[api_key_name][1], dict):
                        bills_data = data[api_key_name][1].get('row', [])
                        self.stdout.write(f'   - Bills data from [1]["row"]: {len(bills_data)} items')
                    elif len(data[api_key_name]) > 0 and isinstance(data[api_key_name][0], dict):
                        head_info = data[api_key_name][0].get('head')
                        if head_info:
                            result_code = head_info[0].get('RESULT', {}).get('CODE', 'UNKNOWN')
                            result_message = head_info[0].get('RESULT', {}).get('MESSAGE', 'No message')
                            self.stdout.write(f'   - API result code: {result_code}')
                            self.stdout.write(f'   - API result message: {result_message}')
                            
                            if result_code.startswith("INFO-200"):
                                self.stdout.write(self.style.WARNING("⚠️ API indicates no bill data available (INFO-200)"))
                        
                        if 'row' in data[api_key_name][0]:
                            bills_data = data[api_key_name][0].get('row', [])
                            self.stdout.write(f'   - Bills data from [0]["row"]: {len(bills_data)} items')

                if bills_data:
                    self.stdout.write(self.style.SUCCESS(f'✅ Found {len(bills_data)} bills in API response:'))
                    for i, bill in enumerate(bills_data, 1):
                        bill_name = bill.get('BILL_NM', 'Unknown')
                        bill_id = bill.get('BILL_ID', 'Unknown')
                        proposer = bill.get('PROPOSER', 'Unknown')
                        self.stdout.write(f'  {i}. {bill_name}')
                        self.stdout.write(f'     - ID: {bill_id}')
                        self.stdout.write(f'     - Proposer: {proposer}')

                    if force_refetch or not current_bills.exists():
                        # Trigger bill fetch
                        self.stdout.write('\n🚀 Triggering bill fetch for this session...')
                        try:
                            if is_celery_available():
                                fetch_session_bills.delay(session_id=session_id, force=True, debug=False)
                                self.stdout.write('✅ Bill fetch task queued with Celery')
                            else:
                                fetch_session_bills(session_id=session_id, force=True, debug=False)
                                self.stdout.write('✅ Bill fetch completed synchronously')

                            # Check results
                            updated_bills = Bill.objects.filter(session=session)
                            self.stdout.write(f'📊 Bills after fetch: {updated_bills.count()}')

                            if updated_bills.exists():
                                self.stdout.write(self.style.SUCCESS('🎉 Bills successfully fetched!'))
                                self.stdout.write('\n💡 To reprocess the PDF with bills:')
                                self.stdout.write(f'   python manage.py test_llm_with_pdf --session-id {session_id} --force')
                            else:
                                self.stdout.write(self.style.ERROR('❌ Bills fetch failed - no bills created'))
                        except Exception as fetch_error:
                            self.stdout.write(self.style.ERROR(f'❌ Error during bill fetch: {fetch_error}'))
                            self.stdout.write(f'Traceback: {traceback.format_exc()}')
                else:
                    self.stdout.write(self.style.WARNING('❌ No bills found in API response'))
                    self.stdout.write('\n🔍 Detailed analysis:')
                    
                    # Check session type
                    if session.title:
                        if '보고' in session.title:
                            self.stdout.write('📋 Session appears to be a reporting session (보고)')
                        elif '심사' in session.title:
                            self.stdout.write('📋 Session appears to be a review session (심사)')
                        elif '의결' in session.title:
                            self.stdout.write('📋 Session appears to be a decision session (의결)')
                        elif '질의' in session.title:
                            self.stdout.write('📋 Session appears to be a Q&A session (질의)')
                    
                    self.stdout.write('\n🔍 Possible reasons for no bills:')
                    self.stdout.write('  1. Procedural or administrative meeting')
                    self.stdout.write('  2. General discussion without specific bills')
                    self.stdout.write('  3. Reporting session (보고사항)')
                    self.stdout.write('  4. Bills discussed but not formally listed in API')
                    self.stdout.write('  5. API data inconsistency or delay')
                    self.stdout.write('  6. Session ID formatting issue')
                    
                    # Try alternative API endpoints
                    self.stdout.write('\n🔄 Trying session details API...')
                    try:
                        if is_celery_available():
                            fetch_session_details.delay(session_id=session_id, force=True, debug=False)
                            self.stdout.write('✅ Session details fetch queued')
                        else:
                            fetch_session_details(session_id=session_id, force=True, debug=False)
                            self.stdout.write('✅ Session details fetch completed')
                    except Exception as details_error:
                        self.stdout.write(self.style.ERROR(f'❌ Error fetching session details: {details_error}'))

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f'❌ API request failed: {e}'))
                self.stdout.write(f'Request details: {params}')
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f'❌ JSON parsing failed: {e}'))
                self.stdout.write(f'Response text (first 500 chars): {response.text[:500]}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Unexpected error: {e}'))
                self.stdout.write(f'Traceback: {traceback.format_exc()}')

        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found in database'))
            self.stdout.write('\n💡 Try fetching the session first:')
            self.stdout.write(f'   python manage.py start_collection --force')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Critical error: {e}'))
            self.stdout.write(f'Traceback: {traceback.format_exc()}')</new_str>
