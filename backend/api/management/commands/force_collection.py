# your_app/management/commands/force_collection.py

import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

# Import the utility function to check Celery availability
from api.tasks import is_celery_available
from api.models import Session

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetches new assembly sessions or re-processes existing PDFs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-api-calls',
            action='store_true',
            help=
            'PDF-only mode: Skips fetching new sessions and re-processes existing PDFs.'
        )
        parser.add_argument('--start-date',
                            type=str,
                            help='Start date in YYYY-MM-DD format.')
        parser.add_argument('--session-id',
                            type=str,
                            help='Process only a single, specific session ID.')
        parser.add_argument('--limit',
                            type=int,
                            help='Limit the number of sessions to process.')
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode (may skip some operations).')

    def handle(self, *args, **options):
        no_api_calls = options['no_api_calls']
        start_date_str = options['start_date']
        session_id = options['session_id']
        limit = options['limit']
        debug = options['debug']

        if no_api_calls:
            self.run_pdf_only_mode(start_date_str, session_id, limit, debug)
        else:
            self.run_full_collection_mode(start_date_str, debug)

    def run_full_collection_mode(self, start_date_str, debug):
        """Default mode: Fetches new sessions from API and processes them."""
        self.stdout.write(
            self.style.SUCCESS(
                '🚀 Starting FULL data collection (API + PDF)...'))

        start_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str,
                                               '%Y-%m-%d').date()
                self.stdout.write(
                    f'📅 Starting collection from specified date: {start_date}')
            except ValueError:
                self.stderr.write(
                    self.style.ERROR('❌ Invalid date format. Use YYYY-MM-DD.'))
                return
        else:
            last_session = Session.objects.order_by('-conf_dt').first()
            if last_session and last_session.conf_dt:
                start_date = last_session.conf_dt
                self.stdout.write(
                    f'📍 Continuing from last session date: {start_date}')
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'No previous sessions found. Starting from today.'))

        try:
            # Use a more robust approach to handle Celery tasks
            try:
                if is_celery_available():
                    self.stdout.write(
                        self.style.SUCCESS(
                            "🚀 Calling 'fetch_continuous_sessions' asynchronously via Celery."
                        ))
                    from api.tasks import fetch_continuous_sessions
                    fetch_continuous_sessions.delay(
                        force=True,
                        debug=debug,
                        start_date=start_date.isoformat() if start_date else None)
                else:
                    raise ImportError("Celery not available")
            except (ImportError, Exception):
                self.stdout.write(
                    self.style.WARNING(
                        "🔄 Calling 'fetch_continuous_sessions' synchronously.")
                )
                # Call the function directly without accessing Celery task attributes
                try:
                    import importlib
                    tasks_module = importlib.import_module('api.tasks')
                    
                    func_name = 'fetch_continuous_sessions'
                    if hasattr(tasks_module, func_name):
                        func = getattr(tasks_module, func_name)
                        # If it's a Celery task, try to get the original function
                        if hasattr(func, 'func'):
                            func = func.func
                        elif hasattr(func, '__wrapped__'):
                            func = func.__wrapped__
                        
                        # Call directly (bound tasks don't need self when called directly)
                        func(
                            force=True,
                            debug=debug,
                            start_date=start_date.isoformat() if start_date else None)
                    else:
                        logger.error(f"Function {func_name} not found in tasks module")
                except Exception as e_fallback:
                    logger.error(f"Failed to call function directly: {e_fallback}")

            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Session fetch task initiated successfully.'))
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'❌ Error initiating collection: {e}'))
            logger.exception("Error in run_full_collection_mode")

    def run_pdf_only_mode(self, start_date_str, session_id, limit, debug):
        """PDF-only mode: Re-processes existing PDFs."""
        self.stdout.write(
            self.style.SUCCESS('📄 Starting PDF-ONLY reprocessing...'))

        sessions_to_process = Session.objects.filter(
            down_url__isnull=False).exclude(
                down_url__exact='').order_by('-conf_dt')

        if session_id:
            sessions_to_process = sessions_to_process.filter(
                conf_id=session_id)
        elif start_date_str:
            try:
                start_date = datetime.strptime(start_date_str,
                                               '%Y-%m-%d').date()
                sessions_to_process = sessions_to_process.filter(
                    conf_dt__gte=start_date)
            except ValueError:
                self.stderr.write(
                    self.style.ERROR('❌ Invalid date format. Use YYYY-MM-DD.'))
                return

        if limit:
            sessions_to_process = sessions_to_process[:limit]

        total_sessions = sessions_to_process.count()
        if total_sessions == 0:
            self.stdout.write(
                self.style.WARNING(
                    'No matching sessions found to re-process.'))
            return

        self.stdout.write(
            f"Found {total_sessions} sessions to re-process PDFs for.")

        # Determine if we're running async or sync once at the start
        use_celery = is_celery_available()
        if use_celery:
            self.stdout.write(
                self.style.SUCCESS(
                    "🚀 Queuing tasks asynchronously via Celery."))
        else:
            self.stdout.write(
                self.style.WARNING("🔄 Running tasks synchronously."))

        for i, session in enumerate(sessions_to_process):
            self.stdout.write(
                f"  -> Processing {i+1}/{total_sessions}: Session {session.conf_id}"
            )
            try:
                # Use a more robust approach to handle Celery tasks
                try:
                    if use_celery:
                        from api.tasks import process_session_pdf
                        process_session_pdf.delay(session_id=session.conf_id,
                                                  force=True,
                                                  debug=debug)
                    else:
                        raise ImportError("Celery not available")
                except (ImportError, Exception):
                    # Call the function directly without trying to access Celery task attributes
                    try:
                        # Import the actual function from tasks module
                        import importlib
                        tasks_module = importlib.import_module('api.tasks')
                        
                        # Get the function by name - this bypasses Celery task wrapper issues
                        func_name = 'process_session_pdf'
                        if hasattr(tasks_module, func_name):
                            func = getattr(tasks_module, func_name)
                            # If it's a Celery task, try to get the original function
                            if hasattr(func, 'func'):
                                func = func.func
                            elif hasattr(func, '__wrapped__'):
                                func = func.__wrapped__
                            
                            # Call the function directly (bound tasks don't need self when called directly)
                            func(session_id=session.conf_id, force=True, debug=debug)
                        else:
                            logger.error(f"Function {func_name} not found in tasks module")
                    except Exception as e_fallback:
                        logger.error(f"Failed to call function directly: {e_fallback}")
                        continue
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f'❌ Error processing task for session {session.conf_id}: {e}'
                    ))
                logger.exception(
                    f"Error in run_pdf_only_mode for session {session.conf_id}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                '✅ All PDF reprocessing tasks have been initiated.'))
