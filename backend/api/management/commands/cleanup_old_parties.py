
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Party, Speaker, Statement
from collections import defaultdict


class Command(BaseCommand):
    help = 'Clean up old and invalid party names from the system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN - No changes will be made')
        
        # Define problematic/old party names that should be cleaned up
        problematic_parties = [
            '대한독립촉성국민회',
            '한나라당', 
            '민주자유당',
            '정보없음',
            '민주정의당',
            '신민당',
            '바른정당',
            '한국당',
            '정의당',  # Old version
            '무소속',
            '',
            ' ',
        ]
        
        # Define current 22nd Assembly parties (official names)
        current_parties = {
            '더불어민주당': '더불어민주당',
            '국민의힘': '국민의힘', 
            '조국혁신당': '조국혁신당',
            '진보당': '진보당',
            '개혁신당': '개혁신당',
            '새로운미래': '새로운미래'
        }
        
        # Party name mappings for consolidation
        party_mappings = {
            '민주통합당': '더불어민주당',
            '더불어민주연합': '더불어민주당',
            '자유한국당': '국민의힘',
            '미래통합당': '국민의힘',
            '국민의미래': '새로운미래',
            '한나라당': '국민의힘',  # Historical mapping
            '민주자유당': '더불어민주당',  # Historical mapping
        }
        
        self.stdout.write('🧹 Step 1: Analyzing current party data...')
        
        # Get all speakers and analyze their party data
        speakers = Speaker.objects.all()
        party_analysis = defaultdict(lambda: {
            'speakers': [],
            'statements': 0,
            'needs_cleanup': False
        })
        
        for speaker in speakers:
            party_list = speaker.get_party_list()
            if not party_list:
                party_analysis['정당정보없음']['speakers'].append(speaker)
                party_analysis['정당정보없음']['needs_cleanup'] = True
                continue
                
            # Check each party in the speaker's history
            for party_name in party_list:
                party_analysis[party_name]['speakers'].append(speaker)
                
                # Check if this party needs cleanup
                if (party_name in problematic_parties or 
                    party_name in party_mappings or
                    not party_name.strip()):
                    party_analysis[party_name]['needs_cleanup'] = True
        
        # Show analysis
        self.stdout.write('\n📊 Party Analysis:')
        for party_name, data in sorted(party_analysis.items(), 
                                     key=lambda x: len(x[1]['speakers']), 
                                     reverse=True):
            speaker_count = len(data['speakers'])
            status = '❌ NEEDS CLEANUP' if data['needs_cleanup'] else '✅ OK'
            self.stdout.write(f'   {party_name}: {speaker_count} speakers {status}')
        
        if dry_run:
            self.stdout.write('\n🔍 DRY RUN: No changes made. Run without --dry-run to apply fixes.')
            return
        
        self.stdout.write('\n🔧 Step 2: Cleaning up problematic parties...')
        
        updated_speakers = 0
        deleted_parties = 0
        
        with transaction.atomic():
            # Process each speaker
            for speaker in speakers:
                party_list = speaker.get_party_list()
                
                if not party_list:
                    # Speaker has no party info
                    if speaker.current_party:
                        speaker.current_party = None
                        speaker.plpt_nm = '정당정보없음'
                        speaker.save()
                        updated_speakers += 1
                    continue
                
                # Get the most recent party
                most_recent_party = party_list[-1].strip()
                
                # Apply mappings or cleanup
                if most_recent_party in party_mappings:
                    target_party = party_mappings[most_recent_party]
                    self.stdout.write(f'   🔄 Mapping {speaker.naas_nm}: {most_recent_party} → {target_party}')
                elif most_recent_party in problematic_parties or not most_recent_party:
                    target_party = '정당정보없음'
                    self.stdout.write(f'   🧹 Cleaning {speaker.naas_nm}: {most_recent_party} → {target_party}')
                elif most_recent_party in current_parties:
                    target_party = current_parties[most_recent_party]
                else:
                    # Unknown party, keep as is but log it
                    self.stdout.write(f'   ⚠️  Unknown party for {speaker.naas_nm}: {most_recent_party}')
                    continue
                
                # Update speaker
                speaker.plpt_nm = target_party
                
                if target_party != '정당정보없음':
                    # Get or create the target party
                    party, created = Party.objects.get_or_create(
                        name=target_party,
                        defaults={
                            'description': f'{target_party} - 제22대 국회',
                            'assembly_era': 22
                        }
                    )
                    speaker.current_party = party
                else:
                    speaker.current_party = None
                
                speaker.save()
                updated_speakers += 1
            
            # Remove old/problematic party records
            for party_name in problematic_parties:
                deleted_count = Party.objects.filter(name=party_name).delete()[0]
                if deleted_count > 0:
                    deleted_parties += deleted_count
                    self.stdout.write(f'   🗑️  Deleted party: {party_name}')
            
            # Remove parties that are now mapped to others
            for old_name in party_mappings.keys():
                # Only delete if no speakers are currently pointing to it
                party_qs = Party.objects.filter(name=old_name)
                if party_qs.exists():
                    party = party_qs.first()
                    current_members = Speaker.objects.filter(current_party=party).count()
                    if current_members == 0:
                        party.delete()
                        deleted_parties += 1
                        self.stdout.write(f'   🗑️  Deleted mapped party: {old_name}')
        
        self.stdout.write(f'\n✅ Cleanup completed!')
        self.stdout.write(f'   📝 Updated {updated_speakers} speakers')
        self.stdout.write(f'   🗑️  Deleted {deleted_parties} old parties')
        
        # Show final party counts
        self.stdout.write('\n📊 Final party distribution:')
        final_parties = Party.objects.all()
        for party in final_parties:
            member_count = Speaker.objects.filter(current_party=party).count()
            self.stdout.write(f'   {party.name}: {member_count} members')
        
        orphaned_count = Speaker.objects.filter(current_party__isnull=True).count()
        if orphaned_count > 0:
            self.stdout.write(f'   정당정보없음: {orphaned_count} members')
