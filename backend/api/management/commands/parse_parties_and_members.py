
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
        parser.add_argument(
            '--parties-only',
            action='store_true',
            help='Only create Party objects from existing Speaker data',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        debug = options.get('debug', False)
        parties_only = options.get('parties_only', False)
        
        if parties_only:
            self.stdout.write('🏛️ Creating Party objects from existing Speaker data...')
            self.create_parties_from_speakers()
            self.stdout.write(
                self.style.SUCCESS('✅ Party creation completed!')
            )
            return
        
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
        batch_size = 50  # Process in smaller batches
        total_members = len(all_members)
        
        self.stdout.write(f'📝 Processing {total_members} members in batches of {batch_size}...')
        
        # Track unique parties to create Party objects
        unique_parties = set()
        
        for i in range(0, total_members, batch_size):
            batch = all_members[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_members + batch_size - 1) // batch_size
            
            self.stdout.write(f'⚙️  Processing batch {batch_num}/{total_batches} ({len(batch)} members)...')
            
            for member_data in batch:
                try:
                    naas_cd = member_data.get('NAAS_CD')
                    if not naas_cd:
                        continue
                    
                    party_name = member_data.get('PLPT_NM', '정당정보없음').strip()
                    if party_name and party_name != '정당정보없음':
                        unique_parties.add(party_name)
                    
                    speaker, created = Speaker.objects.update_or_create(
                        naas_cd=naas_cd,
                        defaults={
                            'naas_nm': member_data.get('NAAS_NM', ''),
                            'naas_ch_nm': member_data.get('NAAS_CH_NM', ''),
                            'plpt_nm': party_name,
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
            
            # Show progress after each batch
            self.stdout.write(f'✅ Batch {batch_num} complete. Progress: {created_count} created, {updated_count} updated')
            
            # Small delay to prevent database overload
            import time
            time.sleep(0.1)
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Members processed: {created_count} created, {updated_count} updated')
        )
        
        # Create Party objects from unique party names
        from api.models import Party
        party_created_count = 0
        self.stdout.write(f'📝 Creating Party objects for {len(unique_parties)} unique parties...')
        
        for party_name in unique_parties:
            try:
                party, party_created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={
                        'description': f'{party_name} 정당',
                        'slogan': '',
                        'logo_url': ''
                    }
                )
                if party_created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error creating party {party_name}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Parties processed: {party_created_count} created')
        )

    def create_parties_from_speakers(self):
        """Create Party objects from unique party names in existing Speaker data"""
        from api.models import Party
        
        # Get unique party names from existing speakers
        unique_parties = Speaker.objects.values_list('plpt_nm', flat=True).distinct()
        unique_parties = set(filter(None, unique_parties))  # Remove None/empty values
        
        if '정당정보없음' in unique_parties:
            unique_parties.remove('정당정보없음')
        
        party_created_count = 0
        self.stdout.write(f'📝 Creating Party objects for {len(unique_parties)} unique parties...')
        
        for party_name in unique_parties:
            try:
                party, party_created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={
                        'description': f'{party_name} 정당',
                        'slogan': '',
                        'logo_url': ''
                    }
                )
                if party_created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')
                else:
                    self.stdout.write(f'🔄 Party already exists: {party_name}')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error creating party {party_name}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Parties processed: {party_created_count} created')
        )
