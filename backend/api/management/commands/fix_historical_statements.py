
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement, Party
from django.db.models import Count, Q
from collections import defaultdict

class Command(BaseCommand):
    help = 'Fix statements assigned to historical parties by reassigning them to correct 22nd Assembly parties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--party',
            type=str,
            help='Fix only specific historical party (e.g., "대한독립촉성국민회")',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        party_filter = options.get('party')

        # Historical parties that shouldn't have current statements
        historical_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당',
            '신민당', '바른정당', '한국당', '정보없음'
        ]

        if party_filter:
            historical_parties = [party_filter]

        # Current 22nd Assembly party mappings
        party_mappings = {
            '국민의힘': ['국민의힘', '새누리당', '한나라당', '미래통합당'],
            '더불어민주당': ['더불어민주당', '민주통합당', '민주당', '새정치민주연합'],
            '조국혁신당': ['조국혁신당'],
            '개혁신당': ['개혁신당'],
            '진보당': ['진보당'],
            '기본소득당': ['기본소득당'],
            '사회민주당': ['사회민주당'],
            '무소속': ['무소속']
        }

        self.stdout.write(self.style.SUCCESS('🔧 Fixing statements from historical parties...'))
        self.stdout.write('')

        total_fixed = 0
        speakers_updated = 0

        for historical_party in historical_parties:
            self.stdout.write(f'📋 Processing: {historical_party}')
            self.stdout.write('-' * 60)

            # Find speakers currently assigned to this historical party
            speakers = Speaker.objects.filter(plpt_nm__icontains=historical_party)
            
            if not speakers.exists():
                self.stdout.write(f'   ❌ No speakers found for {historical_party}')
                continue

            # Get statements from these speakers
            statements = Statement.objects.filter(speaker__in=speakers)
            statement_count = statements.count()

            self.stdout.write(f'   👥 Found {speakers.count()} speakers')
            self.stdout.write(f'   💬 Found {statement_count} statements')

            if statement_count == 0:
                continue

            # Analyze each speaker to determine correct party
            speaker_fixes = []
            for speaker in speakers:
                speaker_statements = statements.filter(speaker=speaker)
                stmt_count = speaker_statements.count()

                if stmt_count == 0:
                    continue

                # Get speaker's party history
                party_list = speaker.get_party_list()
                current_party = speaker.get_current_party_name()

                # Determine correct 22nd Assembly party
                correct_party = None
                
                # Check if speaker is actually in 22nd Assembly
                is_22nd = '22' in speaker.gtelt_eraco
                
                if is_22nd:
                    # For 22nd Assembly members, map to correct current party
                    for target_party, variations in party_mappings.items():
                        if any(var in current_party for var in variations):
                            correct_party = target_party
                            break
                    
                    # Special case for Lee Jong-wook (이종욱) - known 국민의힘 member
                    if speaker.naas_nm == '이종욱':
                        correct_party = '국민의힘'

                if correct_party:
                    speaker_fixes.append({
                        'speaker': speaker,
                        'current_incorrect_party': historical_party,
                        'correct_party': correct_party,
                        'statement_count': stmt_count,
                        'party_history': party_list
                    })

            # Display planned changes
            if speaker_fixes:
                self.stdout.write(f'   🔄 Planned fixes for {historical_party}:')
                for fix in speaker_fixes:
                    self.stdout.write(
                        f'     • {fix["speaker"].naas_nm}: '
                        f'{fix["statement_count"]} statements → {fix["correct_party"]}'
                    )

                if not dry_run:
                    # Apply fixes
                    for fix in speaker_fixes:
                        speaker = fix['speaker']
                        correct_party = fix['correct_party']
                        
                        # Update speaker's party mapping
                        # Find or create the correct party
                        try:
                            correct_party_obj = Party.objects.get(name=correct_party, assembly_era=22)
                        except Party.DoesNotExist:
                            correct_party_obj = Party.objects.create(
                                name=correct_party,
                                assembly_era=22,
                                description=f'{correct_party} - 제22대 국회'
                            )

                        # Update speaker's current party
                        speaker.current_party = correct_party_obj
                        
                        # Update party name in plpt_nm to reflect correct mapping
                        party_history = speaker.get_party_list()
                        if party_history:
                            # Replace the historical party with correct party in the last position
                            updated_history = []
                            for i, party in enumerate(party_history):
                                if party == historical_party and i == len(party_history) - 1:
                                    updated_history.append(correct_party)
                                else:
                                    updated_history.append(party)
                            
                            speaker.plpt_nm = '/'.join(updated_history)
                        
                        speaker.save()
                        
                        total_fixed += fix['statement_count']
                        speakers_updated += 1

                    self.stdout.write(f'   ✅ Fixed {len(speaker_fixes)} speakers')
                else:
                    self.stdout.write(f'   🔍 DRY RUN: Would fix {len(speaker_fixes)} speakers')
                    total_fixed += sum(fix['statement_count'] for fix in speaker_fixes)
                    speakers_updated += len(speaker_fixes)

            else:
                self.stdout.write(f'   ⚠️  No fixable speakers found for {historical_party}')

            self.stdout.write('')

        # Summary
        self.stdout.write('=' * 80)
        if dry_run:
            self.stdout.write(self.style.SUCCESS('🔍 DRY RUN SUMMARY'))
            self.stdout.write(f'   Would fix {speakers_updated} speakers')
            self.stdout.write(f'   Would reassign {total_fixed} statements')
        else:
            self.stdout.write(self.style.SUCCESS('✅ COMPLETION SUMMARY'))
            self.stdout.write(f'   Fixed {speakers_updated} speakers')
            self.stdout.write(f'   Reassigned {total_fixed} statements')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('💡 Next steps:'))
        if dry_run:
            self.stdout.write('   1. Review the planned changes above')
            self.stdout.write('   2. Run without --dry-run to apply fixes:')
            self.stdout.write('      python manage.py fix_historical_statements')
        else:
            self.stdout.write('   1. Run analyze_old_party_statements to verify fixes')
            self.stdout.write('   2. Check party distribution with: python manage.py show_old_party_members')
