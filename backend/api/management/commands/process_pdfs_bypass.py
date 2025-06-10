
from django.core.management.base import BaseCommand
from api.models import Session, Statement
from api.tasks import process_session_pdf, model, genai
import requests
import pdfplumber
import tempfile
import os
from pathlib import Path
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Bypass API checks and process PDFs directly from database URLs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            help='Process specific session ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Process all sessions with PDF URLs',
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
            default=100,
            help='Limit number of sessions to process (default: 100)',
        )

    def handle(self, *args, **options):
        session_id = options.get('session_id')
        process_all = options.get('all')
        force = options.get('force')
        debug = options.get('debug')
        limit = options.get('limit')

        # Check LLM availability
        if not model or not genai:
            self.stdout.write(
                self.style.ERROR('❌ Gemini LLM not available. Please check GEMINI_API_KEY in settings.')
            )
            return

        self.stdout.write(self.style.SUCCESS('✅ Gemini LLM is available'))

        if session_id:
            self.process_single_session(session_id, force, debug)
        elif process_all:
            self.process_all_sessions(force, debug, limit)
        else:
            self.stdout.write(
                self.style.ERROR('❌ Please provide either --session-id or --all')
            )

    def process_single_session(self, session_id, force, debug):
        """Process a single session by ID"""
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'🔍 Processing session: {session_id}')
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

            # Process the PDF directly
            success = self.process_pdf_direct(session, force, debug)
            
            if success and not debug:
                # Check results
                statement_count = session.statements.count()
                self.stdout.write(f'📊 Total statements: {statement_count}')
                
                if statement_count > 0:
                    latest_statements = session.statements.order_by('-created_at')[:3]
                    self.stdout.write('📝 Sample statements:')
                    for stmt in latest_statements:
                        self.stdout.write(
                            f'  - {stmt.speaker.naas_nm}: {stmt.text[:100]}...'
                        )
                        if stmt.sentiment_score is not None:
                            self.stdout.write(f'    Sentiment: {stmt.sentiment_score:.2f}')

        except Session.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Session {session_id} not found in database')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error processing session {session_id}: {e}')
            )

    def process_all_sessions(self, force, debug, limit):
        """Process all sessions with PDF URLs"""
        self.stdout.write(f'🔍 Finding sessions with PDF URLs...')

        # Find sessions with PDFs
        sessions_query = Session.objects.exclude(down_url='').exclude(down_url__isnull=True)
        
        if not force:
            # Only process sessions without statements
            sessions_query = sessions_query.filter(statements__isnull=True).distinct()

        sessions_to_process = sessions_query[:limit]
        total_sessions = sessions_to_process.count()

        self.stdout.write(f'📊 Found {total_sessions} sessions to process')

        if total_sessions == 0:
            self.stdout.write('ℹ️ No sessions need processing')
            return

        processed_count = 0
        success_count = 0

        for session in sessions_to_process:
            self.stdout.write(f'\n--- Processing session {session.conf_id} ({processed_count + 1}/{total_sessions}) ---')
            self.stdout.write(f'📄 Title: {session.title or session.conf_knd}')

            try:
                success = self.process_pdf_direct(session, force, debug)
                if success:
                    success_count += 1
                    if not debug:
                        statement_count = session.statements.count()
                        self.stdout.write(f'✅ Success: {statement_count} statements created')
                else:
                    self.stdout.write('❌ Failed to process PDF')

            except Exception as e:
                self.stdout.write(f'❌ Error: {e}')

            processed_count += 1

            # Brief pause between sessions
            if processed_count < total_sessions:
                time.sleep(2)

        self.stdout.write(f'\n🎉 Processing complete: {success_count}/{processed_count} sessions successful')

    def process_pdf_direct(self, session, force, debug):
        """Process PDF directly without API checks"""
        try:
            self.stdout.write(f'📥 Downloading PDF from: {session.down_url}')
            
            # Download PDF
            response = requests.get(session.down_url, timeout=120, stream=True)
            response.raise_for_status()

            # Create temporary file
            temp_dir = Path("temp_files")
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_pdf_path = temp_dir / f"session_{session.conf_id}_{int(time.time())}.pdf"

            with open(temp_pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.stdout.write(f'✅ PDF downloaded: {temp_pdf_path}')

            # Extract text
            self.stdout.write('📄 Extracting text from PDF...')
            full_text = ""
            
            with pdfplumber.open(temp_pdf_path) as pdf:
                total_pages = len(pdf.pages)
                self.stdout.write(f'📖 Processing {total_pages} pages...')
                
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=3)
                    if page_text:
                        full_text += page_text + "\n"
                    
                    if (i + 1) % 20 == 0:
                        self.stdout.write(f'📄 Processed {i+1}/{total_pages} pages...')

            if not full_text.strip():
                self.stdout.write('❌ No text extracted from PDF')
                return False

            self.stdout.write(f'✅ Extracted {len(full_text)} characters')

            if debug:
                self.stdout.write('🐛 DEBUG MODE: Showing sample text...')
                self.stdout.write('-' * 50)
                self.stdout.write(full_text[:1000] + '...' if len(full_text) > 1000 else full_text)
                self.stdout.write('-' * 50)
                
                # Count speaker markers
                speaker_count = full_text.count('◯')
                self.stdout.write(f'🗣️ Found {speaker_count} speaker markers (◯)')
                
                # Get bill names from database to show what would be sent to LLM
                bill_names = list(session.bills.values_list('bill_nm', flat=True))
                bills_context_str = ", ".join(bill_names) if bill_names else "General Discussion"
                
                self.stdout.write(f'📋 Bills context: {len(bill_names)} bills found')
                
                # Show what would be sent to LLM by calling the text processing functions
                from api.tasks import clean_pdf_text
                cleaned_text = clean_pdf_text(full_text)
                
                # Get bill names to show complete LLM context
                bill_names = list(session.bills.values_list('bill_nm', flat=True))
                bills_context_str = ", ".join(bill_names) if bill_names else "General Discussion"
                
                # Show the exact text that would be sent to LLM discovery function
                self.stdout.write('🤖 COMPLETE TEXT THAT WOULD BE SENT TO LLM DISCOVERY:')
                self.stdout.write('=' * 100)
                self.stdout.write(f'📋 Known bills context: {bills_context_str}')
                self.stdout.write('-' * 50)
                self.stdout.write('📄 FULL CLEANED TEXT:')
                self.stdout.write(cleaned_text)
                self.stdout.write('=' * 100)
                self.stdout.write(f'📏 Total text length: {len(cleaned_text)} characters')
                self.stdout.write(f'📊 Known bills count: {len(bill_names)}')
                
                # Show text statistics
                line_count = cleaned_text.count('\n')
                speaker_markers = cleaned_text.count('◯')
                self.stdout.write(f'📈 Text statistics:')
                self.stdout.write(f'   - Lines: {line_count}')
                self.stdout.write(f'   - Speaker markers (◯): {speaker_markers}')
                self.stdout.write(f'   - Estimated words: {len(cleaned_text.split())}')
                
                # Show sample sections
                if '◯' in cleaned_text:
                    first_speaker_pos = cleaned_text.find('◯')
                    sample_section = cleaned_text[first_speaker_pos:first_speaker_pos+500] if first_speaker_pos != -1 else cleaned_text[:500]
                    self.stdout.write(f'📝 Sample section (first 500 chars from first speaker):')
                    self.stdout.write(f'"{sample_section}..."')
                
                return True

            # Process with LLM (bypass all API checks)
            self.stdout.write('🤖 Processing with LLM...')
            
            # Get bill names from database
            bill_names = list(session.bills.values_list('bill_nm', flat=True))
            bills_context_str = ", ".join(bill_names) if bill_names else "General Discussion"
            
            self.stdout.write(f'📋 Bills context: {len(bill_names)} bills found')

            # Import the PDF processing function
            from api.tasks import process_pdf_text_for_statements
            
            # Process the PDF text
            process_pdf_text_for_statements(
                full_text, 
                session.conf_id, 
                session, 
                bills_context_str, 
                bill_names, 
                debug=False
            )

            self.stdout.write('✅ LLM processing completed')
            return True

        except Exception as e:
            self.stdout.write(f'❌ Error in PDF processing: {e}')
            logger.exception(f"Error processing PDF for session {session.conf_id}")
            return False

        finally:
            # Clean up temporary file
            if 'temp_pdf_path' in locals() and temp_pdf_path.exists():
                try:
                    temp_pdf_path.unlink()
                    self.stdout.write('🗑️ Cleaned up temporary PDF file')
                except OSError as e:
                    self.stdout.write(f'⚠️ Could not delete temp file: {e}')
