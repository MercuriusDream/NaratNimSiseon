"""
Management command to force collect and parse all assembly data.
This command bypasses existing data checks and updates everything.
"""

from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Force collect and parse all assembly data (ignores existing data)'

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

    def handle(self, *args, **options):
        debug = options['debug']
        
        if debug:
            self.stdout.write(
                self.style.SUCCESS('🐛 Starting DEBUG data collection...'))
            self.stdout.write(
                '📋 This will only print data without storing it.')
        else:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting FORCE data collection...'))
            self.stdout.write(
                '⚠️  This will update existing data and may take a while.')

        try:
            from api.tasks import fetch_latest_sessions, is_celery_available

            if is_celery_available():
                self.stdout.write('🚀 Using Celery for async processing')
                fetch_latest_sessions.delay(force=True, debug=debug)
                if debug:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Debug collection task started!'))
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Force collection task started!'))
                self.stdout.write(
                    '📊 Check the logs or run "python manage.py monitor_collection" to track progress.'
                )
            else:
                self.stdout.write(
                    '🔄 Running synchronously (Celery not available)')
                fetch_latest_sessions(force=True, debug=debug)
                if debug:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Debug collection completed!'))
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Force collection completed!'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error starting collection: {e}'))
            logger.error(f"Force collection error: {e}")
