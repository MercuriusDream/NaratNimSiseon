
from django.core.management.base import BaseCommand
from api.tasks import fetch_additional_data_nepjpxkkabqiqpbvk, is_celery_available
from api.models import Speaker
import requests
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Parse and sync party and member data from the Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh of existing data',
        )
        parser.add_argument(
            '--debug',
            action='store_true', 
            help='Debug mode: print data instead of storing it',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        debug = options.get('debug', False)
        
        self.stdout.write('🏛️ Starting party and member data parsing...')
        
        if debug:
            self.stdout.write('🐛 DEBUG mode: Will print data instead of storing')
        
        # Fetch member data from ALLNAMEMBER API
        self.fetch_and_parse_members(force=force, debug=debug)
        
        # Fetch additional party data 
        self.stdout.write('📊 Fetching additional party data...')
        if is_celery_available():
            fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force, debug=debug)
        else:
            fetch_additional_data_nepjpxkkabqiqpbvk(force=force, debug=debug)
        
        self.stdout.write(
            self.style.SUCCESS('✅ Party and member data parsing completed!')
        )

    def fetch_and_parse_members(self, force=False, debug=False):
        """Fetch all assembly members from ALLNAMEMBER API"""
        if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ ASSEMBLY_API_KEY not configured')
            )
            return

        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
        
        # Fetch data with pagination
        all_members = []
        page = 1
        page_size = 100
        
        while True:
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": page,
                "pSize": page_size
            }
            
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                members_data = []
                if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
                    members_data = data['ALLNAMEMBER'][1].get('row', [])
                
                if not members_data:
                    break
                    
                all_members.extend(members_data)
                self.stdout.write(f'📥 Fetched page {page}: {len(members_data)} members')
                
                if len(members_data) < page_size:
                    break
                    
                page += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error fetching page {page}: {e}')
                )
                break
        
        self.stdout.write(f'📊 Total members fetched: {len(all_members)}')
        
        if debug:
            self.stdout.write('🐛 DEBUG: Sample member data:')
            if all_members:
                self.stdout.write(json.dumps(all_members[0], indent=2, ensure_ascii=False))
            return
        
        # Process and save members
        created_count = 0
        updated_count = 0
        
        for member_data in all_members:
            try:
                naas_cd = member_data.get('NAAS_CD')
                if not naas_cd:
                    continue
                
                speaker, created = Speaker.objects.update_or_create(
                    naas_cd=naas_cd,
                    defaults={
                        'naas_nm': member_data.get('NAAS_NM', ''),
                        'naas_ch_nm': member_data.get('NAAS_CH_NM', ''),
                        'plpt_nm': member_data.get('PLPT_NM', '정당정보없음'),
                        'elecd_nm': member_data.get('ELECD_NM') or None,
                        'elecd_div_nm': member_data.get('ELECD_DIV_NM') or None,
                        'cmit_nm': member_data.get('CMIT_NM') or None,
                        'blng_cmit_nm': member_data.get('BLNG_CMIT_NM', ''),
                        'rlct_div_nm': member_data.get('RLCT_DIV_NM', ''),
                        'gtelt_eraco': member_data.get('GTELT_ERACO', ''),
                        'ntr_div': member_data.get('NTR_DIV', ''),
                        'naas_pic': member_data.get('NAAS_PIC', '')
                    }
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error processing member {member_data.get("NAAS_NM", "Unknown")}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Members processed: {created_count} created, {updated_count} updated')
        )
