"""
Management command to force collect and parse all assembly data.
This command bypasses existing data checks and updates everything.
"""

from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions
from api.models import Session
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Force collect and parse all assembly data (continues from last session)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Limit number of sessions to process (default: 100)')
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it')
        parser.add_argument(
            '--restart',
            action='store_true',
            help='Restart from beginning instead of continuing')
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start processing from specific date (YYYY-MM-DD format)')
        parser.add_argument(
            '--start-session',
            type=str,
            help='Start processing from specific session ID (e.g., 54810)')

    def handle(self, *args, **options):
        debug = options['debug']
        restart = options['restart']
        start_date_str = options.get('start_date')
        start_session_id = options.get('start_session')
        
        # Find the last processed session or use specified starting point
        last_session = None
        start_date = None
        
        if start_date_str:
            # Use specified start date
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                self.stdout.write(f'📅 Starting from specified date: {start_date}')
            except ValueError:
                self.stdout.write(self.style.ERROR(f'❌ Invalid date format: {start_date_str}. Use YYYY-MM-DD'))
                return
        elif start_session_id:
            # Use specified session ID to find start date
            try:
                specified_session = Session.objects.get(conf_id=start_session_id)
                start_date = specified_session.conf_dt
                self.stdout.write(f'📍 Starting from specified session: {specified_session.conf_id} ({specified_session.conf_dt})')
                self.stdout.write(f'🔄 Continuing collection from: {start_date}')
            except Session.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Session {start_session_id} not found in database'))
                return
        elif not restart:
            # Auto-find last processed session
            last_session = Session.objects.order_by('-conf_dt', '-created_at').first()
            if last_session:
                start_date = last_session.conf_dt
                self.stdout.write(f'📍 Last processed session: {last_session.conf_id} ({last_session.conf_dt})')
                self.stdout.write(f'🔄 Continuing collection from: {start_date}')
            else:
                self.stdout.write('📍 No previous sessions found, starting from beginning')
        else:
            self.stdout.write('🔄 Restarting collection from beginning (--restart flag used)')
        
        if debug:
            self.stdout.write(
                self.style.SUCCESS('🐛 Starting DEBUG data collection...'))
            self.stdout.write(
                '📋 This will only print data without storing it.')
        else:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting CONTINUOUS data collection...'))
            self.stdout.write(
                '⚠️  This will update existing data and may take a while.')

        try:
            from api.tasks import fetch_continuous_sessions, is_celery_available

            if is_celery_available():
                self.stdout.write('🚀 Using Celery for async processing')
                fetch_continuous_sessions.delay(
                    force=True, 
                    debug=debug, 
                    start_date=start_date.isoformat() if start_date else None
                )
                if debug:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Debug collection task started!'))
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Continuous collection task started!'))
                self.stdout.write(
                    '📊 Check the logs or run "python manage.py monitor_collection" to track progress.'
                )
            else:
                self.stdout.write(
                    '🔄 Running synchronously (Celery not available)')
                # Call the function directly without self parameter when Celery is not available
                fetch_continuous_sessions(
                    self=None,  # Pass None for self when calling directly
                    force=True, 
                    debug=debug, 
                    start_date=start_date.isoformat() if start_date else None
                )
                if debug:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Debug collection completed!'))
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Continuous collection completed!'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error starting collection: {e}'))
            logger.error(f"Force collection error: {e}")
            # Print full traceback for debugging
            import traceback
            self.stdout.write(self.style.ERROR(f'📋 Full error details: {traceback.format_exc()}'))
