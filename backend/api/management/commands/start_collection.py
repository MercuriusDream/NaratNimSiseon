
from django.core.management.base import BaseCommand
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start data collection from Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force collection even if recent data exists',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode',
        )

    def handle(self, *args, **options):
        force = options['force']
        debug = options['debug']

        self.stdout.write(
            self.style.SUCCESS('Starting data collection...')
        )

        try:
            # Import the utility function to check Celery availability
            from api.tasks import is_celery_available
            
            use_celery = is_celery_available()
            
            if use_celery:
                self.stdout.write("🚀 Running with Celery (asynchronous)")
                try:
                    from api.tasks import fetch_latest_sessions
                    fetch_latest_sessions.delay(force=force, debug=debug)
                    self.stdout.write(
                        self.style.SUCCESS('✅ Data collection task queued successfully')
                    )
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f'❌ Error queuing Celery task: {e}')
                    )
                    self.stdout.write("🔄 Falling back to synchronous execution...")
                    use_celery = False
            
            if not use_celery:
                self.stdout.write("🔄 Celery not available, running synchronously")
                try:
                    # Import and run the direct version
                    from api.tasks import fetch_continuous_sessions_direct
                    fetch_continuous_sessions_direct(force=force, debug=debug)
                    self.stdout.write(
                        self.style.SUCCESS('✅ Data collection completed successfully')
                    )
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f'❌ Error in synchronous execution: {e}')
                    )
                    logger.exception("Error in start_collection command")

        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'❌ Critical error in data collection: {e}')
            )
            logger.exception("Critical error in start_collection command")
