# your_app/management/commands/force_collection.py

import logging
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone

# Import the actual task functions directly
from api.tasks import (fetch_continuous_sessions, process_session_pdf,
                       is_celery_available)
from api.models import Session

logger = logging.getLogger(__name__)


# Helper decorator to handle calling Celery tasks properly in sync/async mode
def celery_or_sync(task_func):
    """
    A decorator that calls a Celery task either asynchronously with .delay()
    or synchronously by calling its underlying wrapped function directly.
    """

    def wrapper(*args, **kwargs):
        # Get task name safely
        try:
            task_name = task_func.__name__
        except (AttributeError, Exception):
            # Fallback if __name__ is not accessible (common with Celery proxies)
            task_name = str(task_func).split('.')[-1] if hasattr(task_func, '__module__') else 'unknown_task'
        
        if is_celery_available():
            logger.info(f"🚀 Calling '{task_name}' asynchronously via Celery.")
            task_func.delay(*args, **kwargs)
        else:
            logger.info(f"🔄 Calling '{task_name}' synchronously.")
            # Call the actual Python function wrapped by the @shared_task decorator
            if hasattr(task_func, '__wrapped__'):
                # For bound tasks, the first argument 'self' is not passed in a direct call
                task_func.__wrapped__(None, *args, **kwargs)
            else:
                task_func(*args, **kwargs)

    return wrapper


class Command(BaseCommand):
    help = 'Fetches new assembly sessions or re-processes existing PDFs.'

    def add_arguments(self, parser):
        # --- Mode selection ---
        parser.add_argument(
            '--no-api-calls',
            action='store_true',
            help=
            'PDF-only mode: Skips fetching new sessions from the API and re-processes existing PDFs.'
        )
        # --- Filtering and Options ---
        parser.add_argument(
            '--start-date',
            type=str,
            help=
            'Start date in YYYY-MM-DD format. Used for both fetching and PDF reprocessing.'
        )
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
        # Extract options
        no_api_calls = options['no_api_calls']
        start_date_str = options['start_date']
        session_id = options['session_id']
        limit = options['limit']
        debug = options['debug']

        if no_api_calls:
            self.run_pdf_only_mode(start_date_str, session_id, limit, debug)
        else:
            self.run_full_collection_mode(start_date_str, session_id, debug)

    def run_full_collection_mode(self, start_date_str, session_id, debug):
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
            # Auto-find last processed session date if no start date is given
            last_session = Session.objects.order_by('-conf_dt').first()
            if last_session and last_session.conf_dt:
                start_date = last_session.conf_dt
                self.stdout.write(
                    f'📍 Continuing from last session date: {start_date}')
            else:
                self.stdout.write(
                    self.style.WARNING(
                        'No previous sessions found. Starting from today.'))

        # Prepare the call to the Celery task
        # The decorator will handle sync/async execution
        task_runner = celery_or_sync(fetch_continuous_sessions)

        try:
            task_runner(
                force=
                True,  # In full mode, we always want to update session details
                debug=debug,
                start_date=start_date.isoformat() if start_date else None)
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Session fetch task initiated successfully.'))
            self.stdout.write('📊 Check logs for progress.')
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f'❌ Error initiating collection: {e}'))
            logger.exception("Error in run_full_collection_mode")

    def run_pdf_only_mode(self, start_date_str, session_id, limit, debug):
        """PDF-only mode: Re-processes existing PDFs without calling session list APIs."""
        self.stdout.write(
            self.style.SUCCESS('📄 Starting PDF-ONLY reprocessing...'))

        # Build the queryset for sessions to re-process
        sessions_to_process = Session.objects.filter(
            down_url__isnull=False).exclude(
                down_url__exact='').order_by('-conf_dt')

        if session_id:
            sessions_to_process = sessions_to_process.filter(
                conf_id=session_id)
            self.stdout.write(f"Targeting single session: {session_id}")
        elif start_date_str:
            try:
                start_date = datetime.strptime(start_date_str,
                                               '%Y-%m-%d').date()
                sessions_to_process = sessions_to_process.filter(
                    conf_dt__gte=start_date)
                self.stdout.write(
                    f"Targeting sessions from date: {start_date}")
            except ValueError:
                self.stderr.write(
                    self.style.ERROR('❌ Invalid date format. Use YYYY-MM-DD.'))
                return

        if limit:
            sessions_to_process = sessions_to_process[:limit]
            self.stdout.write(f"Limiting to {limit} sessions.")

        total_sessions = sessions_to_process.count()
        if total_sessions == 0:
            self.stdout.write(
                self.style.WARNING(
                    'No matching sessions with PDF URLs found in the database to re-process.'
                ))
            return

        self.stdout.write(
            f"Found {total_sessions} sessions to re-process PDFs for.")

        # Prepare the call to the Celery task
        task_runner = celery_or_sync(process_session_pdf)

        for i, session in enumerate(sessions_to_process):
            self.stdout.write(
                f"  -> Queuing {i+1}/{total_sessions}: Session {session.conf_id} ({session.conf_dt})"
            )
            try:
                # Call the task for each session. The decorator handles sync/async.
                task_runner(session_id=session.conf_id,
                            force=True,
                            debug=debug)
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f'❌ Error queuing task for session {session.conf_id}: {e}'
                    ))
                logger.exception(
                    f"Error in run_pdf_only_mode for session {session.conf_id}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                '✅ All PDF reprocessing tasks have been initiated.'))
