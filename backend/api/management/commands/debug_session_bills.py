
from django.core.management.base import BaseCommand
from api.models import Session, Bill
from api.tasks import fetch_session_bills, fetch_session_details
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Debug and fix session bill data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            required=True,
            help='Session ID to debug',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fetch missing bills',
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        fix = options['fix']
        
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'🔍 Debugging session: {session_id}')
            self.stdout.write(f'📄 Session: {session.title or session.conf_knd}')
            self.stdout.write(f'📅 Date: {session.conf_dt}')
            self.stdout.write(f'🏛️ Committee: {session.cmit_nm}')
            
            # Check existing bills
            bills = Bill.objects.filter(session=session)
            self.stdout.write(f'📊 Bills found: {bills.count()}')
            
            if bills.exists():
                self.stdout.write('📋 Existing bills:')
                for bill in bills:
                    self.stdout.write(f'  - {bill.bill_nm} (ID: {bill.bill_id})')
            else:
                self.stdout.write('⚠️ No bills found for this session')
                
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
                        
                        # Check the actual API response
                        self.stdout.write('🔍 This could mean:')
                        self.stdout.write('  1. The session has no bills in the assembly database')
                        self.stdout.write('  2. The VCONFBILLLIST API returned no data for this session')
                        self.stdout.write('  3. The session ID format is incorrect')
                        self.stdout.write('  4. The session is a general assembly meeting without specific bills')
                else:
                    self.stdout.write('💡 Use --fix to attempt fetching bills from the API')
            
        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found'))
