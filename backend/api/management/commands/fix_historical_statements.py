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
    help = 'Revert historical party changes and fix speakers by calling API to get their actual 22nd Assembly party'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--revert-only',
            action='store_true',
            help=
            'Only revert the historical party changes without applying fixes',
        )
        parser.add_argument(
            '--name',
            type=str,
            help='Specific speaker name to fix (optional)',
        )
        parser.add_argument(
            '--target-party',
            type=str,
            help='Target party to assign to the speaker (optional)',
        )
        parser.add_argument(
            '--speaker-code',
            type=str,
            help='Specific speaker code to target when multiple speakers have same name (optional)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        revert_only = options.get('revert_only', False)
        speaker_name = options.get('name')
        target_party = options.get('target_party')
        speaker_code = options.get('speaker_code')

        if speaker_name and target_party:
            self.handle_specific_speaker(speaker_name, target_party, dry_run, speaker_code)
            return

        self.stdout.write(
            self.style.SUCCESS(
                '🔄 Step 1: Reverting historical party markings...'))

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')

        # Revert parties back to 22nd Assembly
        historical_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당', '신민당', '정보없음'
        ]

        reverted_parties = 0
        for party_name in historical_parties:
            try:
                parties = Party.objects.filter(name=party_name)
                if parties.exists():
                    for party in parties:
                        if not dry_run:
                            party.assembly_era = 22  # Revert back to 22nd Assembly
                            party.save()
                        reverted_parties += 1
                        self.stdout.write(
                            f'   ✅ Reverted {party_name} back to 22nd Assembly'
                        )
            except Exception as e:
                self.stdout.write(f'   ❌ Error reverting {party_name}: {e}')

        self.stdout.write(
            f'📊 Reverted {reverted_parties} parties back to assembly_era=22')

        if revert_only:
            self.stdout.write('')
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ REVERT COMPLETE - Historical party markings have been undone'
                ))
            return

        # Now proceed with the proper fix
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                '🔧 Step 2: Finding speakers with historical parties who made statements in 22nd Assembly...'
            ))

        # Find speakers who have historical parties AND have 22nd Assembly statements
        speakers_with_statements = Speaker.objects.filter(
            statements__session__era_co='제22대'
        ).filter(
            Q(plpt_nm__icontains='대한독립촉성국민회') | Q(plpt_nm__icontains='한나라당')
            | Q(plpt_nm__icontains='민주자유당') | Q(plpt_nm__icontains='민주정의당')
            | Q(plpt_nm__icontains='신민당') | Q(plpt_nm__icontains='정보없음')
            | Q(plpt_nm='정보없음') | Q(current_party__name__icontains='정보없음')
            | Q(current_party__name__icontains='한나라당')
            | Q(current_party__name='정보없음')
            | Q(current_party__name='한나라당')
        ).distinct()

        self.stdout.write(
            f'   Found {speakers_with_statements.count()} speakers with historical parties who have 22nd Assembly statements'
        )

        # Process each speaker
        fixes_applied = 0
        api_calls_made = 0
        removed_speakers = 0

        for speaker in speakers_with_statements:
            statement_count = Statement.objects.filter(
                speaker=speaker, session__era_co='제22대').count()

            self.stdout.write(
                f'🔄 Processing {speaker.naas_nm} ({statement_count} statements in 22nd Assembly)'
            )
            self.stdout.write(f'   Current party info: {speaker.plpt_nm}')
            current_party_name = speaker.current_party.name if speaker.current_party else 'None'
            self.stdout.write(f'   Current party object: {current_party_name}')

            # Special handling for 정보없음 speakers - remove them completely
            if ('정보없음' in speaker.plpt_nm
                    or (speaker.current_party
                        and '정보없음' in speaker.current_party.name)):

                self.stdout.write(
                    f'   🗑️  Found 정보없음 speaker: {speaker.naas_nm} - completely removing'
                )

                if not dry_run:
                    # Delete ALL statements for this speaker (not just 22nd Assembly)
                    Statement.objects.filter(speaker=speaker).delete()
                    speaker.delete()
                    removed_speakers += 1
                    self.stdout.write(
                        f'   ✅ Completely removed {speaker.naas_nm} and all their statements'
                    )
                else:
                    self.stdout.write(
                        f'   🔍 DRY RUN: Would completely remove {speaker.naas_nm}'
                    )
                    removed_speakers += 1
                continue

            # Call API to get their actual 22nd Assembly party
            raw_22nd_party = self.fetch_22nd_assembly_party(speaker.naas_nm)

            if raw_22nd_party:
                api_calls_made += 1
                current_party = speaker.get_current_party_name()

                # Clean up the party name - extract the most recent/relevant party
                actual_22nd_party = self.clean_party_name(raw_22nd_party)

                self.stdout.write(f'   🧹 Cleaned API party: {raw_22nd_party} → {actual_22nd_party}')

                # Check if the cleaned API party is different and is not a historical party
                if (actual_22nd_party != current_party
                        and actual_22nd_party not in historical_parties
                        and actual_22nd_party
                        not in ['정당정보없음', '무소속', '', '정보없음']):

                    self.stdout.write(
                        f'   ✅ Found correct 22nd Assembly party: {actual_22nd_party} (was: {current_party})'
                    )

                    if not dry_run:
                        self.update_speaker_party(speaker, actual_22nd_party)
                        fixes_applied += 1
                    else:
                        self.stdout.write(
                            f'   🔍 DRY RUN: Would update {speaker.naas_nm} to {actual_22nd_party}'
                        )
                        fixes_applied += 1
                else:
                    self.stdout.write(
                        f'   ⚠️  API party not suitable for update: {actual_22nd_party}'
                    )
            else:
                # For 한나라당 speakers, if API fails, try mapping to 국민의힘
                if ('한나라당' in speaker.plpt_nm
                        or (speaker.current_party
                            and '한나라당' in speaker.current_party.name)):
                    self.stdout.write(f'   🔄 한나라당 speaker - mapping to 국민의힘')
                    if not dry_run:
                        self.update_speaker_party(speaker, '국민의힘')
                        fixes_applied += 1
                    else:
                        self.stdout.write(
                            f'   🔍 DRY RUN: Would update {speaker.naas_nm} to 국민의힘'
                        )
                        fixes_applied += 1
                else:
                    self.stdout.write(
                        f'   ❌ Could not fetch 22nd Assembly data for {speaker.naas_nm}'
                    )

        # Summary
        self.stdout.write('')
        self.stdout.write('📊 Summary:')
        self.stdout.write(f'   Parties reverted: {reverted_parties}')
        self.stdout.write(f'   API calls made: {api_calls_made}')
        if dry_run:
            self.stdout.write(f'   Would fix: {fixes_applied} speakers')
            self.stdout.write(
                f'   Would remove: {removed_speakers} 정보없음 speakers')
        else:
            self.stdout.write(f'   Fixed: {fixes_applied} speakers')
            self.stdout.write(f'   Removed: {removed_speakers} 정보없음 speakers')

        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ DRY RUN COMPLETE - Use --dry-run=false to apply changes'
                ))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ FIXES COMPLETE - Historical parties reverted, speakers updated, and problematic parties cleaned up'
                ))

    def handle_specific_speaker(self, speaker_name, target_party, dry_run, speaker_code=None):
        """Handle updating a specific speaker to a target party"""
        self.stdout.write(
            self.style.SUCCESS(
                f'🎯 Updating specific speaker: {speaker_name} → {target_party}'
            ))

        try:
            # Direct lookup instead of iteration
            if speaker_code:
                speaker = Speaker.objects.get(naas_cd=speaker_code)
                if speaker.naas_nm != speaker_name:
                    self.stdout.write(
                        self.style.ERROR(f'   ❌ Speaker code {speaker_code} does not match name {speaker_name}')
                    )
                    return
            else:
                speaker = Speaker.objects.get(naas_nm=speaker_name)

            current_party_name = speaker.get_current_party_name()
            self.stdout.write(f'   Current party: {current_party_name}')

            if current_party_name == target_party:
                self.stdout.write(f'   ✅ Speaker already in {target_party}')
                return

            if not dry_run:
                self.update_speaker_party(speaker, target_party)
                self.stdout.write(f'   ✅ Updated {speaker_name} to {target_party}')
            else:
                self.stdout.write(f'   🔍 DRY RUN: Would update {speaker_name} to {target_party}')

        except Speaker.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'   ❌ Speaker not found: {speaker_name}')
            )
        except Speaker.MultipleObjectsReturned:
            speakers = Speaker.objects.filter(naas_nm=speaker_name)
            self.stdout.write(
                self.style.ERROR(f'   ❌ Multiple speakers found with name: {speaker_name}')
            )
            self.stdout.write('   📋 Available speakers:')
            for speaker in speakers:
                current_party_name = speaker.get_current_party_name()
                self.stdout.write(f'      🏷️  Code: {speaker.naas_cd}, Party: {current_party_name}, Era: {speaker.gtelt_eraco}')
            self.stdout.write('   💡 Use --speaker-code=<code> to specify which speaker')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'   ❌ Error updating {speaker_name}: {e}')
            )

    def fetch_22nd_assembly_party(self, speaker_name):
        """Fetch speaker's 22nd Assembly party from ALLNAMEMBER API"""
        try:
            if not hasattr(
                    settings,
                    'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
                logger.error("ASSEMBLY_API_KEY not configured")
                return None

            url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "NAAS_NM": speaker_name,
                "Type": "json",
                "pSize": 10
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
                party_name = member_data.get('PLPT_NM', '')

                # Check if this is 22nd Assembly data
                if ('22' in era or '제22대' in era) and party_name:
                    self.stdout.write(
                        f'      🌐 API returned 22nd Assembly party: {party_name} (Era: {era})'
                    )
                    return party_name

            return None

        except Exception as e:
            logger.error(
                f"Error fetching speaker details for {speaker_name}: {e}")
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
                    })

                if created:
                    self.stdout.write(
                        f'      ✨ Created new party: {new_party_name}')

                # Update speaker's current party
                speaker.current_party = correct_party

                # Replace the plpt_nm with just the correct current party
                speaker.plpt_nm = new_party_name
                speaker.save()

                # Update party history
                SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                SpeakerPartyHistory.objects.create(speaker=speaker,
                                                   party=correct_party,
                                                   order=0,
                                                   is_current=True)

                self.stdout.write(
                    f'      ✅ Updated {speaker.naas_nm} to {new_party_name}')

        except Exception as e:
            logger.error(f"Error updating speaker {speaker.naas_nm}: {e}")
            self.stdout.write(
                f'      ❌ Failed to update {speaker.naas_nm}: {e}')

    def clean_party_name(self, party_name):
        """Clean complex party name strings to extract the most relevant current party"""
        if not party_name:
            return party_name

        # Split by slash and get individual parties
        parties = [p.strip() for p in party_name.split('/') if p.strip()]

        if not parties:
            return party_name

        # Priority mapping for current 22nd Assembly parties
        priority_parties = [
            '더불어민주당',
            '국민의힘', 
            '조국혁신당',
            '진보당',
            '개혁신당',
            '새로운미래',
            '무소속'
        ]

        # Look for priority parties first (most recent/relevant)
        for priority_party in priority_parties:
            if priority_party in parties:
                return priority_party

        # If no priority party found, return the last (most recent) party
        return parties[-1]