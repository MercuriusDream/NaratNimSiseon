
from django.core.management.base import BaseCommand
from api.tasks import process_session_pdf, is_celery_available
from api.models import Session
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process PDF transcripts for sessions to extract statements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            help='Process PDF for a specific session ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing of existing data',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit number of sessions to process (default: 10)',
        )

    def handle(self, *args, **options):
        session_id = options.get('session_id')
        force = options.get('force')
        debug = options.get('debug')
        limit = options.get('limit')
        
        if session_id:
            self.stdout.write(f'Processing PDF for session: {session_id}')
            if is_celery_available():
                process_session_pdf.delay(session_id, force=force, debug=debug)
                self.stdout.write(self.style.SUCCESS('✅ PDF processing task queued'))
            else:
                from api.tasks import process_session_pdf_direct
                process_session_pdf_direct(session_id=session_id, force=force, debug=debug)
                self.stdout.write(self.style.SUCCESS('✅ PDF processing completed'))
        else:
            self.stdout.write(f'Processing PDFs for up to {limit} sessions...')
            
            # Find sessions with PDFs but no statements
            sessions_with_pdfs = Session.objects.exclude(down_url='').exclude(down_url__isnull=True)
            
            if not force:
                # Only process sessions without statements
                sessions_with_pdfs = sessions_with_pdfs.filter(statements__isnull=True).distinct()
            
            sessions_to_process = sessions_with_pdfs[:limit]
            
            self.stdout.write(f'Found {sessions_to_process.count()} sessions to process')
            
            processed_count = 0
            for session in sessions_to_process:
                self.stdout.write(f'Processing session: {session.conf_id}')
                
                if is_celery_available():
                    process_session_pdf.delay(session.conf_id, force=force, debug=debug)
                else:
                    from api.tasks import process_session_pdf_direct
                    process_session_pdf_direct(session_id=session.conf_id, force=force, debug=debug)
                
                processed_count += 1
            
            if is_celery_available():
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Queued PDF processing for {processed_count} sessions')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Processed PDFs for {processed_count} sessions')
                )
