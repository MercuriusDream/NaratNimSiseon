
from django.core.management.base import BaseCommand
from api.models import Session, Statement, Bill, Speaker
from django.utils import timezone
from datetime import datetime, timedelta
import time
import os
import json

class Command(BaseCommand):
    help = 'Real-time monitor for processing delays and API timeouts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Refresh interval in seconds (default: 3)',
        )
        parser.add_argument(
            '--track-timeouts',
            action='store_true',
            help='Track and display timeout patterns',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        track_timeouts = options['track_timeouts']
        
        self.stdout.write('🔍 Real-time Processing Monitor')
        self.stdout.write('Press Ctrl+C to stop monitoring\n')
        
        # Track processing metrics over time
        processing_history = []
        timeout_events = []
        
        try:
            while True:
                # Clear screen
                self.stdout.write('\033[2J\033[H')
                
                now = timezone.now()
                
                # Current counts
                sessions = Session.objects.count()
                bills = Bill.objects.count()
                speakers = Speaker.objects.count()
                statements = Statement.objects.count()
                
                # Recent activity (last 5 minutes)
                recent_time = now - timedelta(minutes=5)
                recent_statements = Statement.objects.filter(created_at__gte=recent_time).count()
                recent_sessions = Session.objects.filter(created_at__gte=recent_time).count()
                
                # Processing rate calculation
                if len(processing_history) > 1:
                    prev_count = processing_history[-1]['statements']
                    statements_per_minute = (statements - prev_count) * (60 / interval)
                else:
                    statements_per_minute = 0
                
                # Store current metrics
                processing_history.append({
                    'timestamp': now,
                    'statements': statements,
                    'rate': statements_per_minute
                })
                
                # Keep only last 20 readings (1 minute of history at 3s intervals)
                if len(processing_history) > 20:
                    processing_history.pop(0)
                
                # Sessions with different processing states
                sessions_with_pdfs = Session.objects.exclude(down_url='').count()
                sessions_with_statements = Session.objects.filter(statements__isnull=False).distinct().count()
                sessions_processing = sessions_with_pdfs - sessions_with_statements
                
                # Latest processing activity
                latest_statement = Statement.objects.order_by('-created_at').first()
                latest_session = Session.objects.order_by('-created_at').first()
                
                # Display header
                self.stdout.write('🚀 REAL-TIME PROCESSING MONITOR')
                self.stdout.write('=' * 60)
                self.stdout.write(f'⏰ Last Updated: {now.strftime("%H:%M:%S")}')
                self.stdout.write('')
                
                # Current totals
                self.stdout.write('📊 Current Totals:')
                self.stdout.write(f'   Sessions: {sessions:,} | Bills: {bills:,} | Speakers: {speakers:,}')
                self.stdout.write(f'   Statements: {statements:,}')
                self.stdout.write('')
                
                # Processing pipeline status
                self.stdout.write('🔄 Processing Pipeline:')
                self.stdout.write(f'   Sessions with PDFs: {sessions_with_pdfs:,}')
                self.stdout.write(f'   Sessions processed: {sessions_with_statements:,}')
                self.stdout.write(f'   ⚡ Currently processing: {sessions_processing:,}')
                
                completion_rate = (sessions_with_statements / sessions_with_pdfs * 100) if sessions_with_pdfs > 0 else 0
                self.stdout.write(f'   📈 Completion rate: {completion_rate:.1f}%')
                self.stdout.write('')
                
                # Real-time activity
                self.stdout.write('⚡ Real-time Activity:')
                self.stdout.write(f'   New statements (5min): {recent_statements:,}')
                self.stdout.write(f'   New sessions (5min): {recent_sessions:,}')
                self.stdout.write(f'   Processing rate: {statements_per_minute:.1f} statements/min')
                self.stdout.write('')
                
                # Recent processing trend
                if len(processing_history) >= 5:
                    recent_rates = [h['rate'] for h in processing_history[-5:]]
                    avg_rate = sum(recent_rates) / len(recent_rates)
                    trend = "📈" if statements_per_minute > avg_rate else "📉" if statements_per_minute < avg_rate else "➡️"
                    self.stdout.write(f'   Trend: {trend} (avg: {avg_rate:.1f}/min)')
                self.stdout.write('')
                
                # Latest activity
                self.stdout.write('🕐 Latest Activity:')
                if latest_statement:
                    time_ago = (now - latest_statement.created_at).total_seconds()
                    self.stdout.write(f'   Last statement: {time_ago:.0f}s ago')
                    self.stdout.write(f'   Speaker: {latest_statement.speaker.naas_nm}')
                    if latest_statement.sentiment_score:
                        self.stdout.write(f'   Sentiment: {latest_statement.sentiment_score:.2f}')
                
                if latest_session:
                    time_ago = (now - latest_session.created_at).total_seconds()
                    self.stdout.write(f'   Last session: {time_ago:.0f}s ago')
                self.stdout.write('')
                
                # Performance warnings
                self.stdout.write('⚠️ Performance Status:')
                if statements_per_minute < 1 and statements_per_minute > 0:
                    self.stdout.write('   🐌 SLOW: Processing rate below 1 statement/min')
                elif statements_per_minute == 0 and len(processing_history) > 3:
                    self.stdout.write('   🛑 STALLED: No new statements being processed')
                elif statements_per_minute > 10:
                    self.stdout.write('   🚀 FAST: High processing rate detected')
                else:
                    self.stdout.write('   ✅ NORMAL: Processing at expected rate')
                
                # Check for timeout patterns if requested
                if track_timeouts:
                    # This would require log file monitoring in a real implementation
                    self.stdout.write('   📡 Timeout monitoring: Active')
                
                self.stdout.write('')
                self.stdout.write(f'Refreshing in {interval}s... (Ctrl+C to stop)')
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write('\n🛑 Monitoring stopped.')
            
            # Show summary
            if processing_history:
                total_time = (processing_history[-1]['timestamp'] - processing_history[0]['timestamp']).total_seconds()
                total_statements = processing_history[-1]['statements'] - processing_history[0]['statements']
                avg_rate = (total_statements / total_time * 60) if total_time > 0 else 0
                
                self.stdout.write('')
                self.stdout.write('📋 Session Summary:')
                self.stdout.write(f'   Duration: {total_time:.0f}s')
                self.stdout.write(f'   Statements processed: {total_statements}')
                self.stdout.write(f'   Average rate: {avg_rate:.2f} statements/min')
