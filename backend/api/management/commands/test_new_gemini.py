
from django.core.management.base import BaseCommand
from django.conf import settings
import os

class Command(BaseCommand):
    help = 'Test new Gemini library format from Google GenAI'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-simple',
            action='store_true',
            help='Run a simple test with the new library',
        )
        parser.add_argument(
            '--test-llm-discovery',
            action='store_true',
            help='Test the LLM discovery functionality',
        )

    def handle(self, *args, **options):
        test_simple = options.get('test_simple', False)
        test_llm_discovery = options.get('test_llm_discovery', False)

        self.stdout.write('🧪 Testing new Google GenAI library format...')

        # Check API key
        if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ GEMINI_API_KEY not found in settings')
            )
            return

        self.stdout.write(f'✅ API Key found: {settings.GEMINI_API_KEY[:10]}...')

        # Test import of new library
        try:
            from google import genai
            from google.genai import types
            self.stdout.write('✅ google.genai imported successfully')
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to import google.genai: {e}')
            )
            self.stdout.write('💡 You may need to install: pip install google-genai')
            return

        # Test client initialization
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            self.stdout.write('✅ GenAI client initialized successfully')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to initialize client: {e}')
            )
            return

        if test_simple:
            self.test_simple_generation(client)
        elif test_llm_discovery:
            self.test_llm_discovery_format(client)
        else:
            self.stdout.write('Use --test-simple or --test-llm-discovery to run specific tests')

    def test_simple_generation(self, client):
        """Test simple text generation with new library"""
        try:
            from google.genai import types
            
            self.stdout.write('🔄 Testing simple text generation...')
            
            model = "gemini-2.5-flash-preview-05-20"
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text="안녕하세요. 간단한 테스트입니다. 한국어로 짧게 응답해주세요.")
                    ],
                ),
            ]
            
            config = types.GenerateContentConfig(
                response_mime_type="text/plain",
            )
            
            response_text = ""
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                response_text += chunk.text
            
            if response_text:
                self.stdout.write(f'✅ Generation successful: {response_text[:200]}...')
            else:
                self.stdout.write('❌ No response text generated')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Simple generation failed: {e}')
            )

    def test_llm_discovery_format(self, client):
        """Test the LLM discovery format from your attached code"""
        try:
            from google.genai import types
            
            self.stdout.write('🔄 Testing LLM discovery format...')
            
            # Sample Korean parliamentary text for testing
            sample_text = """
(14시09분 개의)
◯의장 우원식 의석을 정돈해 주시기 바랍니다.
성원이 되었으므로 제1차 본회의를 개의하겠습니다.

1. 검사징계법 일부개정법률안(김용민 의원 대표발의)(의안번호 2208456)

◯김용민 의원 검사징계법 개정안에 대해서 찬성하는 입장을 밝히고자 토론에 임하게 됐습니다.
검사가 잘못하면 누가 징계를 하고 누가 감찰하고 누가 수사하는지 아십니까? 오로지 검사만 해 왔습니다.
            """
            
            model = "gemini-2.5-flash-preview-05-20"
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=f"""You are a world-class legislative analyst AI. 

**KNOWN BILLS:**
- 검사징계법 일부개정법률안(김용민 의원 대표발의)(의안번호 2208456)

**TRANSCRIPT:**
---
{sample_text}
---

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "bills_found": [
    {{
      "bill_name": "검사징계법 일부개정법률안(김용민 의원 대표발의)(의안번호 2208456)",
      "start_index": 123,
      "end_index": 456,
      "main_policy_category": "법행정제도",
      "policy_subcategories": ["검찰 개혁"],
      "key_policy_phrases": ["검찰에 대한 민주적 통제", "검사 징계"],
      "bill_specific_keywords": ["검사징계법", "법무부장관", "징계청구"],
      "policy_stance": "progressive",
      "bill_analysis": "검찰에 대한 민주적 통제 강화를 위한 징계제도 개선"
    }}
  ],
  "newly_discovered": []
}}"""),
                    ],
                ),
            ]
            
            config = types.GenerateContentConfig(
                response_mime_type="text/plain",
            )
            
            response_text = ""
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                response_text += chunk.text
            
            if response_text:
                self.stdout.write(f'✅ LLM Discovery test successful!')
                self.stdout.write(f'📄 Response length: {len(response_text)} characters')
                self.stdout.write(f'📝 Sample response: {response_text[:300]}...')
                
                # Try to parse as JSON
                try:
                    import json
                    # Clean response
                    clean_response = response_text.strip()
                    if clean_response.startswith("```"):
                        clean_response = clean_response.split("```", 2)[-1].strip()
                    
                    parsed_json = json.loads(clean_response)
                    self.stdout.write(f'✅ Response is valid JSON with {len(parsed_json.get("bills_found", []))} bills found')
                except json.JSONDecodeError as e:
                    self.stdout.write(f'⚠️ Response is not valid JSON: {e}')
            else:
                self.stdout.write('❌ No response text generated')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ LLM Discovery test failed: {e}')
            )

        self.stdout.write(
            self.style.SUCCESS('🎉 New GenAI library test completed!')
        )
