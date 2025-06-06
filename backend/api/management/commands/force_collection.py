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

    def handle(self, *args, **options):
        debug = options['debug']
        restart = options['restart']
        
        # Find the last processed session
        last_session = None
        start_date = None
        
        if not restart:
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
                fetch_continuous_sessions(
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
