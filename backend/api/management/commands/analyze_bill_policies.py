
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Bill
from api.tasks import analyze_bill_policy_content
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Analyze policy content for existing bills using LLM'

    def add_arguments(self, parser):
        parser.add_argument(
            '--bill-id',
            type=str,
            help='Analyze specific bill by ID'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit number of bills to analyze (default: 10)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-analyze bills that already have policy data'
        )

    def handle(self, *args, **options):
        bill_id = options['bill_id']
        limit = options['limit']
        force = options['force']

        if bill_id:
            # Analyze specific bill
            try:
                bill = Bill.objects.get(bill_id=bill_id)
                self.stdout.write(f"Analyzing policy content for bill: {bill.bill_nm}")
                analyze_bill_policy_content(bill)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Successfully analyzed bill {bill_id}')
                )
            except Bill.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f'❌ Bill {bill_id} not found')
                )
        else:
            # Analyze multiple bills
            bills_query = Bill.objects.all()
            
            if not force:
                # Only analyze bills without existing policy data
                bills_query = bills_query.filter(
                    policy_categories__exact=[]
                ).filter(
                    category_analysis__exact=''
                )
            
            bills_to_analyze = bills_query.order_by('-created_at')[:limit]
            
            if not bills_to_analyze:
                self.stdout.write(
                    self.style.WARNING('No bills found to analyze')
                )
                return
            
            self.stdout.write(
                f"Found {bills_to_analyze.count()} bills to analyze"
            )
            
            success_count = 0
            error_count = 0
            
            for bill in bills_to_analyze:
                try:
                    self.stdout.write(
                        f"Analyzing: {bill.bill_nm[:50]}..."
                    )
                    analyze_bill_policy_content(bill)
                    success_count += 1
                    
                    # Small delay to respect rate limits
                    import time
                    time.sleep(2)
                    
                except Exception as e:
                    error_count += 1
                    self.stderr.write(
                        self.style.ERROR(f'❌ Error analyzing {bill.bill_id}: {e}')
                    )
                    continue
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Policy analysis complete: {success_count} successful, {error_count} errors'
                )
            )
