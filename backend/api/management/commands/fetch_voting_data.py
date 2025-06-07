
from django.core.management.base import BaseCommand
from api.models import Bill
from api.tasks import fetch_voting_records, is_celery_available
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch voting records for bills from assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bill-id',
            type=str,
            help='Specific bill ID to fetch voting records for',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch of existing voting records',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of bills to process (default: 50)',
        )

    def handle(self, *args, **options):
        bill_id = options.get('bill_id')
        force = options.get('force', False)
        limit = options.get('limit', 50)

        if bill_id:
            # Fetch voting records for specific bill
            self.stdout.write(f'🗳️ Fetching voting records for bill: {bill_id}')
            try:
                if is_celery_available():
                    fetch_voting_records.delay(bill_id=bill_id, force=force)
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Voting records fetch started for bill {bill_id}')
                    )
                else:
                    fetch_voting_records(bill_id=bill_id, force=force)
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Voting records fetch completed for bill {bill_id}')
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error fetching voting records for bill {bill_id}: {e}')
                )
        else:
            # Fetch voting records for multiple bills
            bills = Bill.objects.all()[:limit]
            self.stdout.write(f'🗳️ Fetching voting records for {bills.count()} bills...')

            success_count = 0
            error_count = 0

            for bill in bills:
                try:
                    if is_celery_available():
                        fetch_voting_records.delay(bill_id=bill.bill_id, force=force)
                    else:
                        fetch_voting_records(bill_id=bill.bill_id, force=force)
                    success_count += 1
                    self.stdout.write(f'✅ Started voting records fetch for {bill.bill_nm}')
                except Exception as e:
                    error_count += 1
                    self.stdout.write(f'❌ Error with {bill.bill_nm}: {e}')

            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Voting records fetch completed: {success_count} success, {error_count} errors'
                )
            )
