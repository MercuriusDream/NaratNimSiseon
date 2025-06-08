
from django.core.management.base import BaseCommand
from api.tasks import fetch_bill_detail_info, is_celery_available
from api.models import Bill
import time


class Command(BaseCommand):
    help = 'Fetch detailed information for bills using BILLINFODETAIL API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bill-id',
            type=str,
            help='Fetch details for a specific bill ID',
        )
        parser.add_argument(
            '--session',
            type=str,
            help='Fetch details for bills in a specific session',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of bills to process (default: 50)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch of existing detailed data',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it',
        )

    def handle(self, *args, **options):
        bill_id = options.get('bill_id')
        session_id = options.get('session')
        limit = options.get('limit')
        force = options.get('force')
        debug = options.get('debug')
        
        if debug:
            self.stdout.write(
                self.style.SUCCESS('🐛 Starting DEBUG bill detail collection...')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting bill detail collection...')
            )

        try:
            if bill_id:
                # Fetch details for specific bill
                self.stdout.write(f'🔍 Fetching details for bill: {bill_id}')
                
                if is_celery_available():
                    fetch_bill_detail_info.delay(bill_id=bill_id, force=force, debug=debug)
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Bill detail fetch task started for {bill_id}!')
                    )
                else:
                    fetch_bill_detail_info(bill_id=bill_id, force=force, debug=debug)
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Bill detail fetch completed for {bill_id}!')
                    )
                    
            elif session_id:
                # Fetch details for bills in specific session
                bills = Bill.objects.filter(session__conf_id=session_id)[:limit]
                self.stdout.write(f'🔍 Found {bills.count()} bills in session {session_id}')
                
                for bill in bills:
                    self.stdout.write(f'📄 Processing bill: {bill.bill_id} - {bill.bill_nm[:50]}...')
                    
                    if is_celery_available():
                        fetch_bill_detail_info.delay(bill_id=bill.bill_id, force=force, debug=debug)
                    else:
                        fetch_bill_detail_info(bill_id=bill.bill_id, force=force, debug=debug)
                        if not debug:
                            time.sleep(1)  # Be respectful to API
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Bill detail fetch tasks started for {bills.count()} bills!')
                )
                
            else:
                # Fetch details for recent bills
                bills = Bill.objects.all().order_by('-created_at')[:limit]
                self.stdout.write(f'🔍 Processing {bills.count()} most recent bills')
                
                for bill in bills:
                    self.stdout.write(f'📄 Processing bill: {bill.bill_id} - {bill.bill_nm[:50]}...')
                    
                    if is_celery_available():
                        fetch_bill_detail_info.delay(bill_id=bill.bill_id, force=force, debug=debug)
                    else:
                        fetch_bill_detail_info(bill_id=bill.bill_id, force=force, debug=debug)
                        if not debug:
                            time.sleep(1)  # Be respectful to API
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Bill detail fetch tasks started for {bills.count()} bills!')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error starting bill detail collection: {e}')
            )
