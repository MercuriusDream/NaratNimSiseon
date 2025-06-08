
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement
from django.db.models import Count, Avg
from collections import defaultdict
import requests
import os
import json

class Command(BaseCommand):
    help = 'Verify all 22nd Assembly members against official nepjpxkkabqiqpbvk API data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update party information based on API data',
        )

    def handle(self, *args, **options):
        update_mode = options.get('update', False)
        
        # Current official 22nd Assembly parties
        official_parties = {
            '국민의힘',
            '더불어민주당', 
            '조국혁신당',
            '개혁신당',
            '진보당',
            '기본소득당',
            '사회민주당',
            '무소속'
        }
        
        self.stdout.write(self.style.SUCCESS('🔍 Verifying all 22nd Assembly members...'))
        
        # Get all speakers from our database who are marked as 22nd Assembly
        db_speakers_22 = Speaker.objects.filter(
            gtelt_eraco__icontains='22'
        ).order_by('naas_nm')
        
        self.stdout.write(f'📊 Found {db_speakers_22.count()} speakers in database marked as 22nd Assembly')
        
        # Fetch official data from nepjpxkkabqiqpbvk API
        assembly_api_key = os.getenv('ASSEMBLY_API_KEY')
        if not assembly_api_key:
            self.stdout.write(self.style.ERROR('❌ ASSEMBLY_API_KEY not found in environment variables'))
            return
        
        self.stdout.write('🌐 Fetching official data from nepjpxkkabqiqpbvk API...')
        
        try:
            url = f"https://open.assembly.go.kr/portal/openapi/nepjpxkkabqiqpbvk?KEY={assembly_api_key}&Type=json&pSize=500"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'nepjpxkkabqiqpbvk' not in data or len(data['nepjpxkkabqiqpbvk']) < 2:
                self.stdout.write(self.style.ERROR('❌ Invalid API response structure'))
                return
            
            api_members = data['nepjpxkkabqiqpbvk'][1].get('row', [])
            self.stdout.write(f'🌐 Fetched {len(api_members)} members from official API')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error fetching API data: {e}'))
            return
        
        # Create lookup dictionaries
        api_members_dict = {}
        api_party_stats = defaultdict(int)
        
        for member in api_members:
            name = member.get('naas_nm', '').strip()
            code = member.get('naas_cd', '').strip()
            party = member.get('plpt_nm', '').strip()
            
            if name and code:
                api_members_dict[code] = {
                    'name': name,
                    'party': party,
                    'data': member
                }
                api_party_stats[party] += 1
        
        self.stdout.write('\n📋 Official API party distribution:')
        for party, count in sorted(api_party_stats.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                status = "✅ Official" if party in official_parties else "❓ Unexpected"
                self.stdout.write(f'   {party}: {count} members {status}')
        
        # Compare database vs API
        self.stdout.write('\n🔍 Comparing database vs API data...')
        
        db_codes = set(db_speakers_22.values_list('naas_cd', flat=True))
        api_codes = set(api_members_dict.keys())
        
        missing_from_db = api_codes - db_codes
        missing_from_api = db_codes - api_codes
        common_codes = db_codes & api_codes
        
        self.stdout.write(f'   📊 Common members: {len(common_codes)}')
        self.stdout.write(f'   📊 Missing from DB: {len(missing_from_db)}')
        self.stdout.write(f'   📊 Missing from API: {len(missing_from_api)}')
        
        if missing_from_db:
            self.stdout.write('\n❌ Members in API but not in database:')
            for code in missing_from_db:
                member = api_members_dict[code]
                self.stdout.write(f'   {member["name"]} ({code}) - {member["party"]}')
        
        if missing_from_api:
            self.stdout.write('\n❌ Members in database but not in API:')
            for code in missing_from_api:
                speaker = db_speakers_22.get(naas_cd=code)
                self.stdout.write(f'   {speaker.naas_nm} ({code}) - {speaker.plpt_nm}')
        
        # Check party mismatches
        self.stdout.write('\n🔍 Checking party information for common members...')
        
        party_mismatches = []
        unofficial_parties_in_db = defaultdict(list)
        
        for speaker in db_speakers_22.filter(naas_cd__in=common_codes):
            api_member = api_members_dict.get(speaker.naas_cd)
            if not api_member:
                continue
                
            api_party = api_member['party']
            db_current_party = speaker.get_current_party_name()
            
            # Check if party matches
            if api_party != db_current_party:
                party_mismatches.append({
                    'speaker': speaker,
                    'db_party': db_current_party,
                    'api_party': api_party
                })
            
            # Track parties not in official list
            if api_party not in official_parties:
                unofficial_parties_in_db[api_party].append(speaker)
        
        if party_mismatches:
            self.stdout.write(f'\n❓ Found {len(party_mismatches)} party mismatches:')
            for mismatch in party_mismatches[:20]:  # Show first 20
                self.stdout.write(
                    f'   {mismatch["speaker"].naas_nm}: '
                    f'DB="{mismatch["db_party"]}" vs API="{mismatch["api_party"]}"'
                )
            if len(party_mismatches) > 20:
                self.stdout.write(f'   ... and {len(party_mismatches) - 20} more')
        
        # Show problematic parties in database
        self.stdout.write('\n🚨 Checking for problematic parties in database...')
        
        problematic_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '정보없음', 
            '민주정의당', '신민당', '바른정당', '한국당'
        ]
        
        for party in problematic_parties:
            count = db_speakers_22.filter(plpt_nm__icontains=party).count()
            if count > 0:
                self.stdout.write(f'   ❌ {party}: {count} members still in database')
        
        # Update mode
        if update_mode:
            self.stdout.write('\n💾 Updating party information based on API data...')
            
            updated_count = 0
            for mismatch in party_mismatches:
                speaker = mismatch['speaker']
                api_party = mismatch['api_party']
                
                # Update the plpt_nm field to match API
                # Find the current party in the plpt_nm and replace it
                parties = speaker.get_party_list()
                if parties:
                    parties[-1] = api_party  # Replace the last (current) party
                    speaker.plpt_nm = '/'.join(parties)
                else:
                    speaker.plpt_nm = api_party
                
                speaker.save()
                updated_count += 1
                
                if updated_count <= 10:  # Show first 10 updates
                    self.stdout.write(f'   ✅ Updated {speaker.naas_nm}: {api_party}')
            
            self.stdout.write(f'\n✅ Updated {updated_count} speakers with correct party information')
        
        # Final summary
        self.stdout.write('\n📊 Final Summary:')
        self.stdout.write(f'   Total API members: {len(api_members)}')
        self.stdout.write(f'   Total DB members: {db_speakers_22.count()}')
        self.stdout.write(f'   Party mismatches: {len(party_mismatches)}')
        
        # Show current database party distribution after updates
        self.stdout.write('\n📈 Current database party distribution (22nd Assembly):')
        db_party_stats = defaultdict(int)
        for speaker in db_speakers_22:
            current_party = speaker.get_current_party_name()
            db_party_stats[current_party] += 1
        
        for party, count in sorted(db_party_stats.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                status = "✅ Official" if party in official_parties else "❓ Check needed"
                self.stdout.write(f'   {party}: {count} members {status}')
        
        if not update_mode and party_mismatches:
            self.stdout.write('\n💡 To fix party mismatches, run with --update flag')
