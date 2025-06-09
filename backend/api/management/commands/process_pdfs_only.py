
from django.core.management.base import BaseCommand
from api.models import Session
from api.tasks import process_session_pdf, is_celery_available
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Process PDFs for sessions (download and extract statements) - skips initial data collection'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            help='Process PDF for a specific session ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process PDFs for all sessions with PDF URLs',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing even if statements exist',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: show extracted statements without saving',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Limit number of sessions to process (default: 50)',
        )
        parser.add_argument(
            '--no-bills',
            action='store_true',
            help='Skip sessions that have no bills associated',
        )

    def handle(self, *args, **options):
        session_id = options.get('session_id')
        process_all = options.get('all')
        force = options.get('force')
        debug = options.get('debug')
        limit = options.get('limit')
        no_bills = options.get('no_bills')

        if session_id:
            self.process_single_session(session_id, force, debug)
        elif process_all:
            self.process_all_sessions_with_pdfs(force, debug, limit, no_bills)
        else:
            self.stdout.write(
                self.style.ERROR('❌ Please provide either --session-id or --all')
            )

    def process_single_session(self, session_id, force, debug):
        """Process PDF for a single session by ID"""
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'🔍 Processing PDF for session: {session_id}')
            self.stdout.write(f'📄 Title: {session.title or "No title"}')
            self.stdout.write(f'🔗 PDF URL: {session.down_url}')

            if not session.down_url:
                self.stdout.write(
                    self.style.ERROR(f'❌ No PDF URL for session {session_id}')
                )
                return

            # Check if statements already exist
            existing_statements = session.statements.count()
            if existing_statements > 0 and not force:
                self.stdout.write(
                    f'ℹ️ Session already has {existing_statements} statements. Use --force to reprocess.'
                )
                return

            # Check if bills exist
            bill_count = session.bills.count()
            self.stdout.write(f'📋 Associated bills: {bill_count}')

            # Process the PDF
            self.stdout.write('🚀 Starting PDF processing...')
            
            if is_celery_available() and not debug:
                process_session_pdf.delay(session_id, force=force, debug=debug)
                self.stdout.write(self.style.SUCCESS('✅ PDF processing task queued'))
            else:
                process_session_pdf(session_id=session_id, force=force, debug=debug)
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
                            if stmt.sentiment_score is not None:
                                self.stdout.write(f'    Sentiment: {stmt.sentiment_score:.2f}')

        except Session.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Session {session_id} not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error processing session {session_id}: {e}')
            )

    def process_all_sessions_with_pdfs(self, force, debug, limit, no_bills):
        """Process PDFs for all sessions that have PDF URLs"""
        self.stdout.write(f'🔍 Finding sessions with PDF URLs...')

        # Build query for sessions with PDFs
        sessions_query = Session.objects.exclude(down_url='').exclude(down_url__isnull=True)
        
        if no_bills:
            # Skip sessions that have no bills
            sessions_query = sessions_query.filter(bills__isnull=False).distinct()
            self.stdout.write('📋 Filtering to sessions that have associated bills')
        
        if not force:
            # Only process sessions without statements
            sessions_query = sessions_query.filter(statements__isnull=True).distinct()
            self.stdout.write('📄 Filtering to sessions without existing statements')

        # Order by date (newest first) and limit
        sessions_to_process = sessions_query.order_by('-conf_dt')[:limit]
        total_sessions = sessions_to_process.count()

        self.stdout.write(f'📊 Found {total_sessions} sessions to process')

        if total_sessions == 0:
            self.stdout.write('ℹ️ No sessions need PDF processing')
            return

        processed_count = 0
        success_count = 0

        for session in sessions_to_process:
            self.stdout.write(f'\n--- Processing session {session.conf_id} ({processed_count + 1}/{total_sessions}) ---')
            self.stdout.write(f'📄 Title: {session.title or session.conf_knd}')
            self.stdout.write(f'📅 Date: {session.conf_dt}')
            
            # Show bill count
            bill_count = session.bills.count()
            self.stdout.write(f'📋 Bills: {bill_count}')

            try:
                if is_celery_available() and not debug:
                    process_session_pdf.delay(session.conf_id, force=force, debug=debug)
                    self.stdout.write('✅ PDF processing task queued')
                    success_count += 1
                else:
                    process_session_pdf(session_id=session.conf_id, force=force, debug=debug)
                    
                    if not debug:
                        statement_count = session.statements.count()
                        self.stdout.write(f'✅ Success: {statement_count} statements created')
                        success_count += 1
                    else:
                        self.stdout.write('✅ Debug mode completed')
                        success_count += 1

            except Exception as e:
                self.stdout.write(f'❌ Error: {e}')

            processed_count += 1

        if is_celery_available() and not debug:
            self.stdout.write(f'\n🎉 Processing complete: {success_count}/{processed_count} sessions queued for PDF processing')
            self.stdout.write('📊 Check logs or run "python manage.py monitor_collection" to track progress')
        else:
            self.stdout.write(f'\n🎉 Processing complete: {success_count}/{processed_count} sessions processed')