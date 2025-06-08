
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement, Party, SpeakerPartyHistory
from django.db.models import Count, Q
from django.db import transaction
from collections import defaultdict
import requests
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix speakers with historical parties by calling API to get their actual 22nd Assembly party'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        # Historical parties that shouldn't have current statements
        historical_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당',
            '신민당', '바른정당', '한국당', '정보없음'
        ]

        self.stdout.write(self.style.SUCCESS('🔧 Finding speakers with historical parties and updating with 22nd Assembly data...'))
        self.stdout.write('')

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')

        # Step 1: Find speakers who have historical parties in their plpt_nm AND have 22nd Assembly statements
        self.stdout.write('📊 Step 1: Finding speakers with historical parties who have 22nd Assembly statements...')

        # Build a complex Q query to find speakers with any historical party in their plpt_nm
        historical_party_q = Q()
        for party in historical_parties:
            historical_party_q |= Q(plpt_nm__icontains=party)

        # Get speakers who have historical parties AND have statements in 22nd Assembly
        problematic_speakers = Speaker.objects.filter(
            historical_party_q,
            statements__session__era_co='22'
        ).distinct()

        self.stdout.write(f'   Found {problematic_speakers.count()} speakers with historical parties who have 22nd Assembly statements')

        # Step 2: For each speaker, call the API to get their actual 22nd Assembly party
        fixes_applied = 0
        api_calls_made = 0

        for speaker in problematic_speakers:
            # Get statement count in 22nd Assembly
            statement_count = Statement.objects.filter(
                speaker=speaker,
                session__era_co='22'
            ).count()

            if statement_count == 0:
                continue

            self.stdout.write(f'🔄 Processing {speaker.naas_nm} ({statement_count} statements)')
            self.stdout.write(f'   Current party info: {speaker.plpt_nm}')

            # Check if this speaker has any historical parties in their party list
            party_list = speaker.get_party_list()
            has_historical = any(party in historical_parties for party in party_list)
            
            if not has_historical:
                self.stdout.write(f'   ✅ No historical parties found in current data')
                continue

            # Fetch actual data from API
            actual_22nd_party = self.fetch_22nd_assembly_party(speaker.naas_nm)
            
            if actual_22nd_party:
                api_calls_made += 1
                current_assigned_party = speaker.get_current_party_name()
                
                if actual_22nd_party != current_assigned_party and actual_22nd_party not in historical_parties:
                    self.stdout.write(f'   ✅ Found correct 22nd Assembly party: {actual_22nd_party} (was: {current_assigned_party})')
                    
                    if not dry_run:
                        self.update_speaker_party(speaker, actual_22nd_party)
                        fixes_applied += 1
                    else:
                        self.stdout.write(f'   🔍 DRY RUN: Would update to {actual_22nd_party}')
                        fixes_applied += 1
                else:
                    self.stdout.write(f'   ⚠️  API party matches current or is also historical: {actual_22nd_party}')
            else:
                self.stdout.write(f'   ❌ Could not fetch 22nd Assembly data for {speaker.naas_nm}')

        # Step 3: Summary
        self.stdout.write('')
        self.stdout.write('📊 Summary:')
        self.stdout.write(f'   API calls made: {api_calls_made}')
        if dry_run:
            self.stdout.write(f'   Would fix: {fixes_applied} speakers')
        else:
            self.stdout.write(f'   Fixed: {fixes_applied} speakers')

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS('✅ DRY RUN COMPLETE - No changes made'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ SPEAKER PARTY FIXES COMPLETE'))

    def fetch_22nd_assembly_party(self, speaker_name):
        """Fetch speaker's 22nd Assembly party from ALLNAMEMBER API"""
        try:
            if not hasattr(settings, 'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
                logger.error("ASSEMBLY_API_KEY not configured")
                return None

            url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "NAAS_NM": speaker_name,
                "Type": "json",
                "pSize": 10  # Get more results to find 22nd Assembly specifically
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            member_data_list = []
            if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
                member_data_list = data['ALLNAMEMBER'][1].get('row', [])

            if not member_data_list:
                return None

            # Look specifically for 22nd Assembly member
            for member_data in member_data_list:
                era = member_data.get('GTELT_ERACO', '')
                # Check if this is 22nd Assembly data
                if '22' in era or '제22대' in era:
                    party_name = member_data.get('PLPT_NM', '')
                    if party_name and party_name != '정당정보없음' and party_name != '':
                        self.stdout.write(f'      🌐 API returned 22nd Assembly party: {party_name} (Era: {era})')
                        return party_name

            # If no specific 22nd Assembly data found, log this
            self.stdout.write(f'      ⚠️  No 22nd Assembly data found in API response for {speaker_name}')
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching speaker details for {speaker_name}: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error for speaker details {speaker_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching speaker details for {speaker_name}: {e}")
        
        return None

    def update_speaker_party(self, speaker, new_party_name):
        """Update speaker's party information with the correct 22nd Assembly party"""
        try:
            with transaction.atomic():
                # Get or create the correct party
                correct_party, created = Party.objects.get_or_create(
                    name=new_party_name,
                    defaults={
                        'description': f'{new_party_name} - 제22대 국회',
                        'assembly_era': 22
                    }
                )

                # Update speaker's current party
                speaker.current_party = correct_party
                
                # Update the plpt_nm field - replace historical parties with correct current party
                party_list = speaker.get_party_list()
                
                # Remove historical parties and add the correct current party
                historical_parties = [
                    '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당',
                    '신민당', '바른정당', '한국당', '정보없음'
                ]
                
                # Filter out historical parties
                updated_party_list = [p for p in party_list if p not in historical_parties]
                
                # Remove the new party if it's already in the list to avoid duplicates
                updated_party_list = [p for p in updated_party_list if p != new_party_name]
                
                # Add the correct party as the most recent
                updated_party_list.append(new_party_name)
                
                # Update the plpt_nm field
                speaker.plpt_nm = '/'.join(updated_party_list)
                speaker.save()

                # Update party history
                SpeakerPartyHistory.objects.filter(speaker=speaker, is_current=True).update(is_current=False)
                SpeakerPartyHistory.objects.get_or_create(
                    speaker=speaker,
                    party=correct_party,
                    defaults={
                        'order': len(updated_party_list) - 1,
                        'is_current': True
                    }
                )

                self.stdout.write(f'      ✅ Updated {speaker.naas_nm} from {"/".join(party_list)} to {speaker.plpt_nm}')

        except Exception as e:
            logger.error(f"Error updating speaker {speaker.naas_nm}: {e}")
            self.stdout.write(f'      ❌ Failed to update {speaker.naas_nm}: {e}')
