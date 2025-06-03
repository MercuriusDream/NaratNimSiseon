
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
            help='Limit number of sessions to process (default: 100)'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting FORCE data collection...')
        )
        self.stdout.write(
            '⚠️  This will update existing data and may take a while.'
        )
        
        try:
            # Force fetch with all sessions
            result = fetch_latest_sessions.delay(force=True)
            
            self.stdout.write(
                self.style.SUCCESS('✅ Force collection task started!')
            )
            self.stdout.write(
                '📊 Check the logs or run "python manage.py monitor_collection" to track progress.'
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error starting collection: {e}')
            )
            logger.error(f"Force collection error: {e}")
