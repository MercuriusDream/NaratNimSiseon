from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions, fetch_session_details, process_session_pdf
from api.models import Session

class Command(BaseCommand):
    help = 'Start collecting data from the National Assembly API'

    def handle(self, *args, **options):
        self.stdout.write('Starting data collection...')
        
        try:
            # Try to run tasks asynchronously with Celery
            fetch_latest_sessions.delay()
            
            # For each session, fetch details and process PDF
            sessions = Session.objects.all()
            for session in sessions:
                fetch_session_details.delay(session.conf_id)
                process_session_pdf.delay(session.conf_id)
            
            self.stdout.write(self.style.SUCCESS('Data collection tasks have been queued'))
            
        except Exception as e:
            # Fallback to synchronous execution if Celery is not available
            self.stdout.write(self.style.WARNING(f'Celery not available ({str(e)}), running tasks synchronously...'))
            
            # Run fetch_latest_sessions synchronously
            fetch_latest_sessions()
            
            # For each session, fetch details and process PDF synchronously
            sessions = Session.objects.all()
            for session in sessions:
                fetch_session_details(session.conf_id)
                process_session_pdf(session.conf_id)
            
            self.stdout.write(self.style.SUCCESS('Data collection completed synchronously')) 