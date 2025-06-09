
from django.core.management.base import BaseCommand
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test Gemini LLM connection and functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--simple-test',
            action='store_true',
            help='Run a simple text generation test',
        )

    def handle(self, *args, **options):
        simple_test = options.get('simple_test', False)

        self.stdout.write('🧪 Testing Gemini LLM connection...')

        # Check API key
        if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ GEMINI_API_KEY not found in settings')
            )
            return

        self.stdout.write(f'✅ API Key found: {settings.GEMINI_API_KEY[:10]}...')

        # Test import
        try:
            import google.generativeai as genai
            self.stdout.write('✅ google.generativeai imported successfully')
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to import google.generativeai: {e}')
            )
            return

        # Test configuration
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.stdout.write('✅ Gemini API configured successfully')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to configure Gemini API: {e}')
            )
            return

        # Test model initialization
        try:
            model = genai.GenerativeModel('gemini-2.0-flash-lite')
            self.stdout.write('✅ Model initialized successfully')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to initialize model: {e}')
            )
            return

        if simple_test:
            # Test simple generation
            try:
                self.stdout.write('🔄 Testing text generation...')
                response = model.generate_content('안녕하세요. 간단한 테스트입니다.')
                
                if response and response.text:
                    self.stdout.write(f'✅ Generation successful: {response.text[:100]}...')
                else:
                    self.stdout.write('❌ No response text generated')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Generation failed: {e}')
                )
                return

        # Test rate limiter status
        try:
            from api.tasks import gemini_rate_limiter, log_rate_limit_status
            self.stdout.write('🔄 Checking rate limiter status...')
            stats = log_rate_limit_status()
            self.stdout.write(f'✅ Rate limiter operational: {stats}')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Rate limiter check failed: {e}')
            )

        self.stdout.write(
            self.style.SUCCESS('🎉 All Gemini tests completed successfully!')
        )tyle.SUCCESS('🎉 All Gemini LLM tests passed!')
        )
