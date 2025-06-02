from django.core.management.base import BaseCommand
from api.tasks import fetch_latest_sessions, fetch_session_details, process_session_pdf
from api.models import Session

class Command(BaseCommand):
    help = 'Start collecting data from the National Assembly API'

    def handle(self, *args, **options):
        self.stdout.write('Starting data collection...')
        
        # Fetch latest sessions
        fetch_latest_sessions.delay()
        
        # For each session, fetch details and process PDF
        sessions = Session.objects.all()
        for session in sessions:
            fetch_session_details.delay(session.conf_id)
            process_session_pdf.delay(session.conf_id)
        
        self.stdout.write(self.style.SUCCESS('Data collection tasks have been queued')) 