
from django.core.management.base import BaseCommand
from api.models import Session
from api.tasks import process_session_pdf, is_celery_available


class Command(BaseCommand):
    help = 'Test LLM-based statement extraction from a PDF'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            required=True,
            help='Session ID to test PDF processing',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: show extracted statements without saving',
        )

    def handle(self, *args, **options):
        session_id = options['session_id']
        debug = options['debug']
        
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'Testing LLM extraction for session: {session_id}')
            self.stdout.write(f'Session: {session}')
            self.stdout.write(f'PDF URL: {session.down_url}')
            
            if not session.down_url:
                self.stdout.write(self.style.ERROR('❌ No PDF URL available for this session'))
                return
            
            # Process the PDF
            if is_celery_available() and not debug:
                process_session_pdf.delay(session_id, force=True, debug=debug)
                self.stdout.write(self.style.SUCCESS('✅ PDF processing task queued'))
            else:
                process_session_pdf(session_id=session_id, force=True, debug=debug)
                self.stdout.write(self.style.SUCCESS('✅ PDF processing completed'))
                
                if not debug:
                    # Check results
                    statement_count = session.statements.count()
                    self.stdout.write(f'📊 Statements created: {statement_count}')
                    
                    if statement_count > 0:
                        latest_statements = session.statements.order_by('-created_at')[:3]
                        self.stdout.write('📝 Latest statements:')
                        for stmt in latest_statements:
                            self.stdout.write(f'  - {stmt.speaker.naas_nm}: {stmt.text[:100]}...')
            
        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
