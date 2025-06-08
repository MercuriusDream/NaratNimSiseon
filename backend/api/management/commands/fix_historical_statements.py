
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement, Party
from django.db.models import Count, Q
from django.conf import settings
import requests
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix all speakers assigned to historical parties by fetching correct data from ALLNAMEMBER API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of speakers to process (for testing)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        limit = options.get('limit')

        # Historical parties that shouldn't have current statements
        historical_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당',
            '신민당', '바른정당', '한국당', '정보없음'
        ]

        # Current 22nd Assembly parties (official)
        current_22nd_parties = {
            '더불어민주당', '국민의힘', '조국혁신당', '개혁신당', 
            '진보당', '기본소득당', '사회민주당', '무소속'
        }

        self.stdout.write(self.style.SUCCESS('🔧 Fixing ALL speakers with historical party assignments...'))
        self.stdout.write('')

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')
        
        if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
            return

        # Find ALL speakers with problematic party assignments
        problematic_speakers = []
        
        for historical_party in historical_parties:
            speakers = Speaker.objects.filter(plpt_nm__icontains=historical_party)
            for speaker in speakers:
                if speaker not in problematic_speakers:
                    problematic_speakers.append(speaker)

        # Also find speakers with any non-current parties
        all_speakers = Speaker.objects.all()
        for speaker in all_speakers:
            current_party = speaker.get_current_party_name()
            if current_party not in current_22nd_parties and speaker not in problematic_speakers:
                problematic_speakers.append(speaker)

        total_speakers = len(problematic_speakers)
        if limit:
            problematic_speakers = problematic_speakers[:limit]
            self.stdout.write(f'📊 Processing {len(problematic_speakers)} of {total_speakers} speakers (limited)')
        else:
            self.stdout.write(f'📊 Processing {total_speakers} speakers total')

        self.stdout.write('')

        fixed_count = 0
        api_call_count = 0
        errors = []

        for i, speaker in enumerate(problematic_speakers, 1):
            self.stdout.write(f'🔄 Processing {i}/{len(problematic_speakers)}: {speaker.naas_nm}')
            
            # Get current problematic party
            current_party = speaker.get_current_party_name()
            self.stdout.write(f'   Current party: {current_party}')

            # Fetch correct data from API
            api_data = self.fetch_speaker_details(speaker.naas_nm)
            api_call_count += 1
            
            if not api_data:
                error_msg = f'❌ Failed to fetch API data for {speaker.naas_nm}'
                self.stdout.write(f'   {error_msg}')
                errors.append(error_msg)
                continue

            api_party = api_data.get('PLPT_NM', '').strip()
            api_era = api_data.get('GTELT_ERACO', '').strip()
            
            self.stdout.write(f'   API party: {api_party}')
            self.stdout.write(f'   API era: {api_era}')

            # Check if this is actually a 22nd Assembly member
            is_22nd_member = '22' in api_era
            
            if not is_22nd_member:
                self.stdout.write(f'   ⚠️  Not a 22nd Assembly member - skipping')
                continue

            # Determine correct party mapping
            correct_party = self.map_to_current_party(api_party)
            
            if correct_party == current_party:
                self.stdout.write(f'   ✅ Already correct: {correct_party}')
                continue

            self.stdout.write(f'   🔄 Fixing: {current_party} → {correct_party}')

            if not dry_run:
                # Update speaker data
                self.update_speaker_data(speaker, api_data, correct_party)
                fixed_count += 1
                self.stdout.write(f'   ✅ Fixed!')
            else:
                fixed_count += 1
                self.stdout.write(f'   🔍 Would fix!')

            self.stdout.write('')

            # Add small delay to be nice to the API
            if api_call_count % 10 == 0:
                import time
                time.sleep(1)

        # Summary
        self.stdout.write('=' * 80)
        if dry_run:
            self.stdout.write(self.style.SUCCESS('🔍 DRY RUN SUMMARY'))
            self.stdout.write(f'   Would fix {fixed_count} speakers')
        else:
            self.stdout.write(self.style.SUCCESS('✅ COMPLETION SUMMARY'))
            self.stdout.write(f'   Fixed {fixed_count} speakers')
        
        self.stdout.write(f'   API calls made: {api_call_count}')
        self.stdout.write(f'   Errors encountered: {len(errors)}')

        if errors:
            self.stdout.write('')
            self.stdout.write('❌ Errors:')
            for error in errors[:10]:  # Show first 10 errors
                self.stdout.write(f'   {error}')
            if len(errors) > 10:
                self.stdout.write(f'   ... and {len(errors) - 10} more errors')

    def fetch_speaker_details(self, speaker_name):
        """Fetch speaker details from ALLNAMEMBER API"""
        try:
            url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "NAAS_NM": speaker_name,
                "Type": "json",
                "pSize": 5
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            member_data_list = []
            if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
                member_data_list = data['ALLNAMEMBER'][1].get('row', [])

            if not member_data_list:
                return None

            # Get the most recent (22nd Assembly) member data
            for member_data in member_data_list:
                era = member_data.get('GTELT_ERACO', '')
                if '22' in era:
                    return member_data
            
            # If no 22nd Assembly data found, return the first result
            return member_data_list[0]

        except Exception as e:
            logger.error(f"Error fetching speaker details for {speaker_name}: {e}")
            return None

    def map_to_current_party(self, api_party):
        """Map API party name to current 22nd Assembly party"""
        if not api_party:
            return '무소속'

        # Direct matches first
        current_parties = {
            '더불어민주당', '국민의힘', '조국혁신당', '개혁신당', 
            '진보당', '기본소득당', '사회민주당', '무소속'
        }
        
        if api_party in current_parties:
            return api_party

        # Party name mappings
        party_mappings = {
            '민주통합당': '더불어민주당',
            '더불어민주연합': '더불어민주당',
            '새정치민주연합': '더불어민주당',
            '민주당': '더불어민주당',
            
            '자유한국당': '국민의힘',
            '미래통합당': '국민의힘',
            '한나라당': '국민의힘',
            '새누리당': '국민의힘',
            
            '국민의미래': '개혁신당',
            '새로운미래': '개혁신당',
            
            '정의당': '진보당',
            '민주노동당': '진보당',
            
            '정보없음': '무소속',
            '': '무소속',
        }

        return party_mappings.get(api_party, api_party)

    def update_speaker_data(self, speaker, api_data, correct_party):
        """Update speaker with correct API data and party"""
        from api.models import Party, SpeakerPartyHistory
        
        # Update speaker fields with fresh API data
        speaker.naas_nm = api_data.get('NAAS_NM', speaker.naas_nm)
        speaker.naas_ch_nm = api_data.get('NAAS_CH_NM', '')
        speaker.plpt_nm = api_data.get('PLPT_NM', correct_party)
        speaker.elecd_nm = api_data.get('ELECD_NM', '')
        speaker.elecd_div_nm = api_data.get('ELECD_DIV_NM', '')
        speaker.cmit_nm = api_data.get('CMIT_NM', '')
        speaker.blng_cmit_nm = api_data.get('BLNG_CMIT_NM', '')
        speaker.rlct_div_nm = api_data.get('RLCT_DIV_NM', '')
        speaker.gtelt_eraco = api_data.get('GTELT_ERACO', '')
        speaker.ntr_div = api_data.get('NTR_DIV', '')
        speaker.naas_pic = api_data.get('NAAS_PIC', '')

        # Get or create the correct party
        correct_party_obj, created = Party.objects.get_or_create(
            name=correct_party,
            defaults={
                'description': f'{correct_party} - 제22대 국회',
                'assembly_era': 22
            }
        )

        # Update current party
        speaker.current_party = correct_party_obj
        speaker.save()

        # Update party history
        SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
        SpeakerPartyHistory.objects.create(
            speaker=speaker,
            party=correct_party_obj,
            order=0,
            is_current=True
        )
