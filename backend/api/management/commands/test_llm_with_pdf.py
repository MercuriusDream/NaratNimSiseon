
from django.core.management.base import BaseCommand
from api.models import Session
from api.tasks import process_session_pdf, is_celery_available
import requests
import pdfplumber
import tempfile
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test LLM extraction with a PDF file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--session-id',
            type=str,
            help='Session ID to test (will download its PDF)',
        )
        parser.add_argument(
            '--pdf-url',
            type=str,
            help='Direct PDF URL to test',
        )
        parser.add_argument(
            '--local-pdf',
            type=str,
            help='Path to local PDF file',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: show extracted statements without saving',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocessing even if statements exist',
        )

    def handle(self, *args, **options):
        session_id = options.get('session_id')
        pdf_url = options.get('pdf_url')
        local_pdf = options.get('local_pdf')
        debug = options.get('debug', False)
        force = options.get('force', False)

        if not any([session_id, pdf_url, local_pdf]):
            self.stdout.write(
                self.style.ERROR('❌ Please provide either --session-id, --pdf-url, or --local-pdf')
            )
            return

        # Test 1: Using existing session
        if session_id:
            self.test_with_session(session_id, debug, force)
        
        # Test 2: Using direct PDF URL
        elif pdf_url:
            self.test_with_url(pdf_url, debug)
        
        # Test 3: Using local PDF file
        elif local_pdf:
            self.test_with_local_file(local_pdf, debug)

    def test_with_session(self, session_id, debug, force):
        """Test with an existing session"""
        try:
            session = Session.objects.get(conf_id=session_id)
            self.stdout.write(f'🧪 Testing LLM extraction for session: {session_id}')
            self.stdout.write(f'📄 Session: {session.title or session.conf_knd}')
            self.stdout.write(f'🔗 PDF URL: {session.down_url}')
            
            if not session.down_url:
                self.stdout.write(self.style.ERROR('❌ No PDF URL available for this session'))
                return

            # Check if statements already exist
            existing_statements = session.statements.count()
            if existing_statements > 0 and not force:
                self.stdout.write(f'ℹ️ Session already has {existing_statements} statements. Use --force to reprocess.')
                return

            # Process the PDF
            self.stdout.write('🚀 Starting PDF processing...')
            
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
                            self.stdout.write(f'    Sentiment: {stmt.sentiment_score}, Bill: {stmt.bill.bill_nm if stmt.bill else "None"}')

        except Session.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Session {session_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))

    def test_with_url(self, pdf_url, debug):
        """Test with a direct PDF URL"""
        self.stdout.write(f'🧪 Testing LLM extraction with PDF URL: {pdf_url}')
        
        try:
            # Download PDF to temporary file
            self.stdout.write('📥 Downloading PDF...')
            response = requests.get(pdf_url, timeout=120, stream=True)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_pdf_path = temp_file.name
            
            self.stdout.write(f'✅ PDF downloaded to: {temp_pdf_path}')
            
            # Process the PDF
            self.test_pdf_extraction(temp_pdf_path, debug)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error downloading PDF: {e}'))
        finally:
            # Clean up temporary file
            if 'temp_pdf_path' in locals() and os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
                self.stdout.write('🗑️ Cleaned up temporary file')

    def test_with_local_file(self, local_pdf, debug):
        """Test with a local PDF file"""
        pdf_path = Path(local_pdf)
        
        if not pdf_path.exists():
            self.stdout.write(self.style.ERROR(f'❌ PDF file not found: {local_pdf}'))
            return
        
        self.stdout.write(f'🧪 Testing LLM extraction with local PDF: {local_pdf}')
        self.test_pdf_extraction(str(pdf_path), debug)

    def test_pdf_extraction(self, pdf_path, debug):
        """Test PDF text extraction and LLM processing"""
        try:
            # Extract text from PDF
            self.stdout.write('📄 Extracting text from PDF...')
            
            full_text = ""
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                self.stdout.write(f'📖 Processing {total_pages} pages...')
                
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=3)
                    if page_text:
                        full_text += page_text + "\n"
                    
                    if (i + 1) % 10 == 0:
                        self.stdout.write(f'📄 Processed {i+1}/{total_pages} pages...')
            
            if not full_text.strip():
                self.stdout.write(self.style.ERROR('❌ No text extracted from PDF'))
                return
            
            self.stdout.write(f'✅ Extracted {len(full_text)} characters from PDF')
            
            # Test LLM availability
            from api.tasks import model, genai
            if not model or not genai:
                self.stdout.write(self.style.ERROR('❌ LLM not available'))
                return
            
            self.stdout.write('✅ LLM is available')
            
            # Show sample of extracted text
            self.stdout.write('📝 Sample extracted text:')
            self.stdout.write('-' * 50)
            self.stdout.write(full_text[:500] + '...' if len(full_text) > 500 else full_text)
            self.stdout.write('-' * 50)
            
            if debug:
                # In debug mode, just show what would be processed
                self.stdout.write('🐛 DEBUG MODE: Would process text with LLM')
                
                # Try to identify speaker markers
                speaker_count = full_text.count('◯')
                self.stdout.write(f'🗣️ Found approximately {speaker_count} speaker markers (◯)')
                
                # Look for bill patterns
                import re
                bill_patterns = re.findall(r'(\d+\.\s*[^◯\n]{20,100}법률안[^◯\n]*)', full_text)
                self.stdout.write(f'📜 Found {len(bill_patterns)} potential bill patterns')
                if bill_patterns:
                    self.stdout.write('📜 Sample bills found:')
                    for pattern in bill_patterns[:3]:
                        self.stdout.write(f'  - {pattern.strip()[:80]}...')
            else:
                self.stdout.write('🤖 This would normally process with the full LLM pipeline')
                self.stdout.write('ℹ️ Use --debug to see analysis without actual processing')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error processing PDF: {e}'))
            logger.exception("Full traceback:")
