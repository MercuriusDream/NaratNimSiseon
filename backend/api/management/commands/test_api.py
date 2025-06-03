
from django.core.management.base import BaseCommand
import requests
from django.conf import settings
import json


class Command(BaseCommand):
    help = 'Test the API response structure and show raw data'

    def handle(self, *args, **options):
        try:
            url = "https://open.assembly.go.kr/portal/openapi/nekcaiymatialqlxr"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": 1,
                "pSize": 10,  # Small test size
                "UNIT_CD": "100022"
            }

            self.stdout.write('🔍 Testing API call...')
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            self.stdout.write('📋 Raw API Response Structure:')
            self.stdout.write(json.dumps(data, indent=2, ensure_ascii=False))

            # Test our parsing logic
            sessions_data = None
            if 'nekcaiymatialqlxr' in data and len(data['nekcaiymatialqlxr']) > 0:
                sessions_data = data['nekcaiymatialqlxr'][0].get('row', [])
            elif 'row' in data:
                sessions_data = data['row']

            self.stdout.write(f'✅ Found {len(sessions_data) if sessions_data else 0} sessions')
            
            if sessions_data and len(sessions_data) > 0:
                self.stdout.write(f'📝 First session example:')
                self.stdout.write(json.dumps(sessions_data[0], indent=2, ensure_ascii=False))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
