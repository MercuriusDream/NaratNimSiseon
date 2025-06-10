
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
                self.stdout.write('🤖 COMPLETE LLM REQUEST PREVIEW:')
                self.stdout.write('=' * 100)
                self.stdout.write(f'📋 Known bills context: {bills_context_str}')
                self.stdout.write('-' * 50)
                self.stdout.write('📄 CLEANED TEXT (that would be analyzed):')
                self.stdout.write(cleaned_text)
                self.stdout.write('=' * 100)
                
                # Show text statistics
                line_count = cleaned_text.count('\n')
                speaker_markers = cleaned_text.count('◯')
                self.stdout.write(f'📈 Text statistics:')
                self.stdout.write(f'   - Total length: {len(cleaned_text)} characters')
                self.stdout.write(f'   - Lines: {line_count}')
                self.stdout.write(f'   - Speaker markers (◯): {speaker_markers}')
                self.stdout.write(f'   - Estimated words: {len(cleaned_text.split())}')
                self.stdout.write(f'   - Known bills count: {len(bill_names)}')
                
                # Show what the actual LLM prompt would look like
                self.stdout.write('\n' + '🔥' * 50)
                self.stdout.write('🔥 COMPLETE LLM PROMPT THAT WOULD BE SENT TO GEMINI:')
                self.stdout.write('🔥' * 50)
                
                # Recreate the exact prompt from extract_statements_with_llm_discovery
                if known_bill_names:
                    known_bills_str = "\n".join(f"- {name}" for name in bill_names)
                else:
                    known_bills_str = "No known bills were provided."
                
                # Policy categories section (simplified for debug)
                policy_categories_section = """**POLICY CATEGORIES:**
- 경제정책: 국가의 재정, 산업, 무역, 조세 등을 통한 경제 운용 및 성장 전략
- 사회정책: 복지, 보건, 교육, 노동 등 사회 전반의 정책
- 외교안보정책: 외교관계, 국방, 통일, 안보 관련 정책
- 법행정제도: 행정개혁, 사법제도, 인권, 법률 제도
- 과학기술정책: 과학기술진흥, IT, 디지털전환, 연구개발
- 문화체육정책: 문화예술, 체육, 관광, 미디어 정책
- 인권소수자정책: 인권보호, 소수자 권익, 차별 방지
- 지역균형정책: 지역개발, 균형발전, 지방자치
- 정치정책: 선거제도, 정당, 정치개혁 관련 정책"""

                full_prompt = f"""You are a world-class legislative analyst AI. Your task is to read a parliamentary transcript
and perfectly segment the entire discussion for all topics, while also analyzing policy content.

**CONTEXT:**
I already know about the following bills. You MUST find the discussion for these if they exist.
--- KNOWN BILLS ---
{known_bills_str}

**YOUR CRITICAL MISSION:**
1. Read the entire transcript below.
2. Identify the exact start and end character index for the complete discussion of each **KNOWN BILL**.
3. Discover any additional bills/topics not in the known list, and identify their discussion spans.
4. For each bill/topic, analyze the policy content and categorize it using the categories below.
5. Return a JSON object with segmentation AND detailed policy analysis.

{policy_categories_section}

**ANALYSIS REQUIREMENTS:**
- For each bill/topic, identify the main policy category and up to 3 subcategories
- Extract 3-7 key policy phrases that represent the core policy elements
- Extract 3-5 bill-specific keywords (technical terms, specific provisions)
- Provide a concise policy analysis (max 80 Korean characters)
- Assess policy stance: progressive/conservative/moderate

**RULES:**
- Ignore any mentions that occur in the table-of-contents or front-matter portion of the document
  (before the Chair officially opens the debate).
- A discussion segment **must** be substantive, containing actual debate or remarks from multiple speakers.
  Do not segment short procedural announcements.
- `bill_name` for known bills MUST EXACTLY MATCH the provided list.
- For new items, create a concise, accurate `bill_name`.
- Use exact category names from the policy categories list above.
- Return **ONLY** the final JSON object.

**TRANSCRIPT:**
---
{cleaned_text}
---

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "bills_found": [
    {{
      "bill_name": "Exact name of a KNOWN bill",
      "start_index": 1234,
      "end_index": 5678,
      "main_policy_category": "경제정책",
      "policy_subcategories": ["확장재정", "중소기업 지원"],
      "key_policy_phrases": ["중소기업 지원", "일자리 창출", "사회안전망"],
      "bill_specific_keywords": ["법인세", "세율", "과세"],
      "policy_stance": "progressive",
      "bill_analysis": "중소기업 지원을 위한 세제 혜택 확대 법안"
    }}
  ],
  "newly_discovered": [
    {{
      "bill_name": "Name of a newly discovered topic",
      "start_index": 2345,
      "end_index": 6789,
      "main_policy_category": "환경/에너지",
      "policy_subcategories": ["탄소세 도입"],
      "key_policy_phrases": ["탄소중립", "재생에너지", "온실가스"],
      "bill_specific_keywords": ["탄소세", "배출권", "그린뉴딜"],
      "policy_stance": "progressive",
      "bill_analysis": "탄소중립 실현을 위한 환경세 도입 법안"
    }}
  ]
}}"""
                
                self.stdout.write(full_prompt)
                self.stdout.write('🔥' * 50)
                self.stdout.write(f'📏 TOTAL PROMPT LENGTH: {len(full_prompt)} characters')
                self.stdout.write(f'📊 ESTIMATED TOKENS: ~{len(full_prompt) // 4}')
                
                # Show sample sections
                if '◯' in cleaned_text:
                    first_speaker_pos = cleaned_text.find('◯')
                    sample_section = cleaned_text[first_speaker_pos:first_speaker_pos+500] if first_speaker_pos != -1 else cleaned_text[:500]
                    self.stdout.write(f'\n📝 Sample section (first 500 chars from first speaker):')
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
