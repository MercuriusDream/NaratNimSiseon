
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
                    
                    # Extract all parties from party history
                    if party_name and party_name != '정당정보없음':
                        party_list = [p.strip() for p in party_name.split('/') if p.strip()]
                        unique_parties.update(party_list)
                    
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
        
        # Create Party objects from clean API data and existing speaker data
        self.fetch_and_create_parties(force=force, debug=debug)
        
        # Process speaker party histories
        self.process_speaker_party_histories()

    def create_parties_from_speakers(self):
        """Create Party objects from clean API data and process speaker histories"""
        self.stdout.write('📝 Creating Party objects from Assembly API data...')
        self.fetch_and_create_parties(force=False, debug=False)
        
        # Also create parties from existing speaker data
        self.stdout.write('📝 Creating Party objects from existing Speaker data...')
        self.create_parties_from_existing_speakers()
        
        # Process speaker party histories
        self.process_speaker_party_histories()

    def fetch_and_create_parties(self, force=False, debug=False):
        """Fetch clean party data from Assembly APIs and create Party objects"""
        from api.models import Party
        
        if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ ASSEMBLY_API_KEY not configured')
            )
            return

        # Try current party composition first (22nd assembly)
        current_parties = self.fetch_current_parties()
        
        # Try historical party data (21st assembly and below)
        historical_parties = self.fetch_historical_parties()
        
        # Combine and deduplicate
        all_parties = {}
        
        # Add current parties
        for party in current_parties:
            party_name = party.get('POLY_NM', '').strip()
            if party_name and party_name not in ['비교섭단체', '합계']:
                all_parties[party_name] = {
                    'name': party_name,
                    'description': f'{party_name} - 현재 의석수: {party.get("N3", 0)}석',
                    'current_seats': party.get('N3', 0)
                }
        
        # Add historical parties
        for party in historical_parties:
            party_name = party.get('PLPT_NM', '').strip()
            if party_name and party_name not in ['합계'] and party_name not in all_parties:
                all_parties[party_name] = {
                    'name': party_name,
                    'description': f'{party_name} - 제21대 국회',
                    'current_seats': 0
                }
        
        if debug:
            self.stdout.write('🐛 DEBUG: Party data to create:')
            for party_name, party_data in all_parties.items():
                self.stdout.write(f'  - {party_name}: {party_data}')
            return
        
        # Create Party objects
        party_created_count = 0
        party_updated_count = 0


    def process_speaker_party_histories(self):
        """Process all speakers and create party history records"""
        from api.models import Party, SpeakerPartyHistory
        
        self.stdout.write('🔄 Processing speaker party histories...')
        
        speakers = Speaker.objects.all()
        processed_count = 0
        
        for speaker in speakers:
            try:
                party_list = speaker.get_party_list()
                if not party_list:
                    continue
                
                # Clear existing history for this speaker
                SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                
                # Create party history records
                for order, party_name in enumerate(party_list):
                    try:
                        party, created = Party.objects.get_or_create(
                            name=party_name,
                            defaults={'description': f'{party_name} - 자동 생성됨'}
                        )
                        
                        is_current = (order == len(party_list) - 1)  # Last party is current
                        
                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=party,
                            order=order,
                            is_current=is_current
                        )
                        
                        # Set current party
                        if is_current:
                            speaker.current_party = party
                            speaker.save(update_fields=['current_party'])
                        
                    except Exception as e:


    def create_parties_from_existing_speakers(self):
        """Create Party objects from existing Speaker data party histories"""
        from api.models import Party
        
        unique_parties = set()
        
        # Get all unique parties from speaker data
        speakers = Speaker.objects.all()
        for speaker in speakers:
            party_list = speaker.get_party_list()
            unique_parties.update(party_list)
        
        self.stdout.write(f'📝 Creating Party objects for {len(unique_parties)} unique parties...')
        
        party_created_count = 0
        
        for party_name in unique_parties:
            if not party_name or party_name == '정당정보없음':
                continue
                
            try:
                party, created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={
                        'description': f'{party_name} - 국회의원 데이터에서 추출',
                        'slogan': '',
                        'logo_url': ''
                    }
                )
                
                if created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error creating party {party_name}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Created {party_created_count} new parties from speaker data')
        )


                        self.stdout.write(f'⚠️  Warning: Could not process party "{party_name}" for {speaker.naas_nm}: {e}')
                        continue
                
                processed_count += 1
                
                if processed_count % 50 == 0:
                    self.stdout.write(f'🔄 Processed {processed_count} speakers...')
                    
            except Exception as e:
                self.stdout.write(f'❌ Error processing speaker {speaker.naas_nm}: {e}')
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Speaker party histories processed: {processed_count} speakers')
        )


        
        self.stdout.write(f'📝 Creating/updating {len(all_parties)} parties from API data...')
        
        for party_name, party_data in all_parties.items():
            try:
                party, created = Party.objects.update_or_create(
                    name=party_name,
                    defaults={
                        'description': party_data['description'],
                        'slogan': '',
                        'logo_url': ''
                    }
                )
                
                if created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')
                else:
                    party_updated_count += 1
                    self.stdout.write(f'🔄 Updated party: {party_name}')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error creating/updating party {party_name}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Parties processed: {party_created_count} created, {party_updated_count} updated')
        )

    def fetch_current_parties(self):
        """Fetch current party composition from nepjpxkkabqiqpbvk API"""
        url = "https://open.assembly.go.kr/portal/openapi/nepjpxkkabqiqpbvk"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "Type": "json"
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'nepjpxkkabqiqpbvk' in data and len(data['nepjpxkkabqiqpbvk']) > 1:
                parties = data['nepjpxkkabqiqpbvk'][1].get('row', [])
                self.stdout.write(f'📥 Fetched {len(parties)} current parties')
                return parties
            
        except Exception as e:
            self.stdout.write(f'⚠️  Warning: Could not fetch current parties: {e}')
        
        return []

    def fetch_historical_parties(self):
        """Fetch historical party data from nedjqrnlavrvcycue API"""
        url = "https://open.assembly.go.kr/portal/openapi/nedjqrnlavrvcycue"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "ORD_NO": "제21대",
            "Type": "json"
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if 'nedjqrnlavrvcycue' in data and len(data['nedjqrnlavrvcycue']) > 1:
                parties = data['nedjqrnlavrvcycue'][1].get('row', [])
                self.stdout.write(f'📥 Fetched {len(parties)} historical parties (21st assembly)')
                return parties
            
        except Exception as e:
            self.stdout.write(f'⚠️  Warning: Could not fetch historical parties: {e}')
        
        return []
