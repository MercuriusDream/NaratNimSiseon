from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions, fetch_session_details
from api.models import Session
import time

class Command(BaseCommand):
    help = 'Start collecting data from the National Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-collection of existing data')
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output')
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it')

    def handle(self, *args, **options):
        self.stdout.write('Starting data collection...')

        force = options['force']
        verbose = options['verbose']
        debug = options['debug']

        if verbose:
            self.stdout.write('📊 Initial database status:')
            self.stdout.write(f'   Sessions: {Session.objects.count()}')

        # Import tasks with fallback capability
        from api.tasks import fetch_latest_sessions, is_celery_available

        if is_celery_available():
            self.stdout.write(self.style.SUCCESS('🚀 Using Celery for async processing'))
            if verbose:
                self.stdout.write('⏳ Tasks will run in background via Celery...')
                self.stdout.write('   Use "python manage.py monitor_collection" to track progress')
        else:
            self.stdout.write(self.style.WARNING('🔄 Celery not available, running synchronously'))

        # Start data collection (will automatically choose sync/async)
        if verbose:
            self.stdout.write('📡 Starting data collection...')

        fetch_latest_sessions(force=force, debug=debug)

        if is_celery_available():
            self.stdout.write(self.style.SUCCESS('✅ Data collection tasks queued'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ Data collection completed synchronously'))
            if verbose:
                final_sessions = Session.objects.count()
                self.stdout.write(f'📊 Final status: {final_sessions} sessions in database')