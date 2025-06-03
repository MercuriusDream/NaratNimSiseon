
from django.core.management.base import BaseCommand
from api.models import Session, Bill, Speaker, Statement
import time

class Command(BaseCommand):
    help = 'Monitor data collection progress in real-time'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Refresh interval in seconds (default: 5)',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        
        self.stdout.write(f'📊 Monitoring data collection (refreshing every {interval}s)')
        self.stdout.write('Press Ctrl+C to stop monitoring\n')
        
        try:
            while True:
                # Clear screen (works in most terminals)
                self.stdout.write('\033[2J\033[H')
                
                # Get current counts
                sessions = Session.objects.count()
                bills = Bill.objects.count()
                speakers = Speaker.objects.count()
                statements = Statement.objects.count()
                
                # Get sessions with PDFs processed
                sessions_with_pdfs = Session.objects.exclude(down_url__isnull=True).exclude(down_url='').count()
                sessions_with_statements = Session.objects.filter(statements__isnull=False).distinct().count()
                
                self.stdout.write('🔄 REAL-TIME DATA COLLECTION MONITOR')
                self.stdout.write('=' * 50)
                self.stdout.write(f'📋 Sessions: {sessions}')
                self.stdout.write(f'📄 Bills: {bills}')
                self.stdout.write(f'👥 Speakers: {speakers}')
                self.stdout.write(f'💬 Statements: {statements}')
                self.stdout.write('')
                self.stdout.write('📊 Processing Status:')
                self.stdout.write(f'   Sessions with PDF URLs: {sessions_with_pdfs}')
                self.stdout.write(f'   Sessions with processed statements: {sessions_with_statements}')
                self.stdout.write('')
                
                if sessions > 0:
                    pdf_percentage = (sessions_with_pdfs / sessions) * 100
                    statement_percentage = (sessions_with_statements / sessions) * 100
                    self.stdout.write(f'   PDF processing: {pdf_percentage:.1f}%')
                    self.stdout.write(f'   Statement extraction: {statement_percentage:.1f}%')
                
                self.stdout.write(f'\n⏰ Last updated: {time.strftime("%Y-%m-%d %H:%M:%S")}')
                self.stdout.write(f'🔄 Next refresh in {interval} seconds...')
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write('\n\n👋 Monitoring stopped')
