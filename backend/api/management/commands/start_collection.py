
from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions, fetch_session_details, process_session_pdf
from api.models import Session
import time

class Command(BaseCommand):
    help = 'Start collecting data from the National Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force fetch all sessions, not just recent ones',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress information',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting data collection...')
        
        force = options['force']
        verbose = options['verbose']
        
        if verbose:
            self.stdout.write('📊 Initial database status:')
            self.stdout.write(f'   Sessions: {Session.objects.count()}')
        
        try:
            # Try to run tasks asynchronously with Celery
            if verbose:
                self.stdout.write('🔄 Attempting to use Celery for async processing...')
            
            fetch_latest_sessions.delay(force=force)
            
            # For each session, fetch details and process PDF
            sessions = Session.objects.all()
            for session in sessions:
                fetch_session_details.delay(session.conf_id, force=force)
                process_session_pdf.delay(session.conf_id, force=force)
            
            self.stdout.write(self.style.SUCCESS('Data collection tasks have been queued'))
            
            if verbose:
                self.stdout.write('⏳ Tasks are running in background via Celery...')
                self.stdout.write('   Use "python manage.py check_data_status" to monitor progress')
            
        except Exception as e:
            # Fallback to synchronous execution if Celery is not available
            self.stdout.write(self.style.WARNING(f'Celery not available ({str(e)}), running tasks synchronously...'))
            
            if verbose:
                self.stdout.write('🔄 Starting synchronous data collection...')
            
            # Run fetch_latest_sessions synchronously
            if verbose:
                self.stdout.write('📡 Fetching latest sessions from API...')
            fetch_latest_sessions(force=force)
            
            if verbose:
                sessions_after_fetch = Session.objects.count()
                self.stdout.write(f'   Found {sessions_after_fetch} sessions')
            
            # For each session, fetch details and process PDF synchronously
            sessions = Session.objects.all()
            total_sessions = sessions.count()
            
            for i, session in enumerate(sessions, 1):
                if verbose:
                    self.stdout.write(f'🔍 Processing session {i}/{total_sessions}: {session.conf_id}')
                
                fetch_session_details(session.conf_id, force=force)
                
                if verbose:
                    self.stdout.write(f'📄 Processing PDF for session {session.conf_id}...')
                process_session_pdf(session.conf_id, force=force)
            
            self.stdout.write(self.style.SUCCESS('Data collection completed synchronously'))
            
            if verbose:
                final_sessions = Session.objects.count()
                self.stdout.write(f'📊 Final database status:')
                self.stdout.write(f'   Sessions: {final_sessions}')
