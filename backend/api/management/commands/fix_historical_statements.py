from django.core.management.base import BaseCommand
from api.models import Speaker, Statement, Party, SpeakerPartyHistory
from django.db.models import Count, Q
from django.db import transaction
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix speakers with historical parties by analyzing their statements and 22nd Assembly activity'

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

        # Current 22nd Assembly parties (official)
        current_22nd_parties = {
            '더불어민주당', '국민의힘', '조국혁신당', '개혁신당', 
            '진보당', '기본소득당', '사회민주당', '무소속'
        }

        self.stdout.write(self.style.SUCCESS('🔧 Fixing speakers using statement analysis...'))
        self.stdout.write('')

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')

        # Step 1: Find speakers with statements in 22nd Assembly sessions
        self.stdout.write('📊 Step 1: Identifying 22nd Assembly active speakers...')

        # Get speakers who have made statements in 22nd Assembly sessions
        active_22nd_speakers = Speaker.objects.filter(
            statements__session__era_co='22'
        ).distinct()

        self.stdout.write(f'   Found {active_22nd_speakers.count()} speakers with 22nd Assembly statements')

        # Step 2: Analyze party distribution from statements
        self.stdout.write('📈 Step 2: Analyzing party patterns from statements...')

        # Get party distribution from recent statements
        party_analysis = defaultdict(lambda: {
            'speakers': set(),
            'statement_count': 0,
            'is_historical': False
        })

        # Analyze statements to find actual party affiliations
        for speaker in active_22nd_speakers:
            current_party = speaker.get_current_party_name()

            # Count statements
            statement_count = Statement.objects.filter(
                speaker=speaker,
                session__era_co='22'
            ).count()

            party_analysis[current_party]['speakers'].add(speaker)
            party_analysis[current_party]['statement_count'] += statement_count
            party_analysis[current_party]['is_historical'] = current_party in historical_parties

        # Step 3: Map speakers to correct parties
        self.stdout.write('🔄 Step 3: Mapping speakers to correct parties...')

        fixes_needed = []

        for party_name, data in party_analysis.items():
            if data['is_historical']:
                self.stdout.write(f'   🔍 Analyzing {len(data["speakers"])} speakers in historical party: {party_name}')

                for speaker in data['speakers']:
                    # Try to infer correct party from similar speakers or context
                    correct_party = self.infer_correct_party(speaker, current_22nd_parties)

                    if correct_party != party_name:
                        fixes_needed.append({
                            'speaker': speaker,
                            'old_party': party_name,
                            'new_party': correct_party
                        })

        self.stdout.write(f'   📋 Found {len(fixes_needed)} speakers needing party fixes')

        # Step 4: Apply fixes
        if fixes_needed:
            self.stdout.write('🛠️  Step 4: Applying party fixes...')

            if not dry_run:
                with transaction.atomic():
                    self.apply_party_fixes(fixes_needed)

            # Show summary
            party_changes = defaultdict(int)
            for fix in fixes_needed:
                party_changes[f"{fix['old_party']} → {fix['new_party']}"] += 1

            self.stdout.write('')
            self.stdout.write('📊 Summary of changes:')
            for change, count in party_changes.items():
                action = "Would change" if dry_run else "Changed"
                self.stdout.write(f'   {action} {count} speakers: {change}')

        # Step 5: Clean up empty historical parties
        if not dry_run:
            self.stdout.write('🧹 Step 5: Cleaning up empty historical parties...')
            self.cleanup_empty_historical_parties(historical_parties)

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS('✅ DRY RUN COMPLETE - No changes made'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ PARTY FIXES COMPLETE'))

    def infer_correct_party(self, speaker, current_22nd_parties):
        """Infer correct party based on speaker context and patterns"""

        # Method 1: Check if speaker has statements with other party members
        recent_statements = Statement.objects.filter(
            speaker=speaker,
            session__era_co='22'
        ).select_related('session').order_by('-session__conf_dt')[:10]

        # Analyze committee or session context to infer party
        party_context = defaultdict(int)

        for statement in recent_statements:
            # Get other speakers in same session
            session_speakers = Statement.objects.filter(
                session=statement.session
            ).exclude(speaker=speaker).values_list('speaker__get_current_party_name', flat=True)

            for other_party in session_speakers:
                if other_party in current_22nd_parties:
                    party_context[other_party] += 1

        # Method 2: Use name patterns or committee assignments
        if speaker.elecd_nm:  # Electoral district
            # Find other speakers from same district
            same_district_speakers = Speaker.objects.filter(
                elecd_nm=speaker.elecd_nm,
                statements__session__era_co='22'
            ).exclude(naas_cd=speaker.naas_cd).distinct()

            for other_speaker in same_district_speakers:
                other_party = other_speaker.get_current_party_name()
                if other_party in current_22nd_parties:
                    party_context[other_party] += 2  # Weight district matches higher

        # Method 3: Committee analysis
        if speaker.cmit_nm:
            committee_speakers = Speaker.objects.filter(
                cmit_nm__icontains=speaker.cmit_nm,
                statements__session__era_co='22'
            ).exclude(naas_cd=speaker.naas_cd).distinct()

            for other_speaker in committee_speakers:
                other_party = other_speaker.get_current_party_name()
                if other_party in current_22nd_parties:
                    party_context[other_party] += 1

        # Return most likely party or default to 무소속
        if party_context:
            return max(party_context.items(), key=lambda x: x[1])[0]

        return '무소속'

    def apply_party_fixes(self, fixes_needed):
        """Apply the party fixes in bulk"""

        for fix in fixes_needed:
            speaker = fix['speaker']
            new_party_name = fix['new_party']

            # Get or create the correct party
            correct_party, created = Party.objects.get_or_create(
                name=new_party_name,
                defaults={
                    'description': f'{new_party_name} - 제22대 국회',
                    'assembly_era': 22
                }
            )

            # Update speaker
            speaker.plpt_nm = new_party_name
            speaker.current_party = correct_party
            speaker.save()

            # Update party history
            SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
            SpeakerPartyHistory.objects.create(
                speaker=speaker,
                party=correct_party,
                order=0,
                is_current=True
            )

    def cleanup_empty_historical_parties(self, historical_parties):
        """Remove historical parties that have no current members"""

        for party_name in historical_parties:
            try:
                party = Party.objects.get(name=party_name, assembly_era=22)
                current_members = Speaker.objects.filter(current_party=party).count()

                if current_members == 0:
                    party.delete()
                    self.stdout.write(f'   🗑️  Removed empty historical party: {party_name}')

            except Party.DoesNotExist:
                continue