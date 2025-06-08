
from django.core.management.base import BaseCommand
from api.models import Party, Speaker, Statement
from django.db.models import Count
from collections import defaultdict


class Command(BaseCommand):
    help = 'Fix duplicate party names and consolidate party data properly'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN - No actual changes will be made\n')
        else:
            self.stdout.write('🔧 FIXING party duplicates and consolidating data\n')

        # Step 1: Clean up problematic party names
        self.fix_problematic_party_names(dry_run)
        
        # Step 2: Update speakers to use the most recent party name
        self.update_speaker_current_parties(dry_run)
        
        # Step 3: Clean up duplicate Party records
        self.consolidate_duplicate_parties(dry_run)
        
        # Step 4: Show final statistics
        self.show_party_statistics()

    def fix_problematic_party_names(self, dry_run):
        """Fix speakers with problematic party name patterns"""
        self.stdout.write('🔍 Step 1: Fixing problematic party names in Speaker records...')
        
        # Party name mappings for consolidation
        party_mappings = {
            # All variations should map to 더불어민주당
            '민주통합당': '더불어민주당',
            '더불어민주연합': '더불어민주당',
            # Add other mappings as needed
        }
        
        speakers_updated = 0
        
        for speaker in Speaker.objects.all():
            if not speaker.plpt_nm:
                continue
                
            # Get party list and clean it
            party_list = speaker.get_party_list()
            
            if not party_list:
                continue
            
            # Clean each party name and apply mappings
            cleaned_parties = []
            for party in party_list:
                # Apply mapping if exists
                if party in party_mappings:
                    cleaned_party = party_mappings[party]
                    self.stdout.write(f'  📝 Mapping {party} -> {cleaned_party} for {speaker.naas_nm}')
                else:
                    cleaned_party = party
                cleaned_parties.append(cleaned_party)
            
            # Remove duplicates while preserving order
            final_parties = []
            for party in cleaned_parties:
                if party not in final_parties:
                    final_parties.append(party)
            
            # Get the most recent (last) party
            current_party_name = final_parties[-1] if final_parties else '정당정보없음'
            
            # Update plpt_nm if it changed
            new_plpt_nm = '/'.join(final_parties)
            if speaker.plpt_nm != new_plpt_nm:
                if not dry_run:
                    speaker.plpt_nm = new_plpt_nm
                    speaker.save()
                speakers_updated += 1
                self.stdout.write(f'  ✅ Updated {speaker.naas_nm}: {speaker.plpt_nm} -> {new_plpt_nm}')
        
        self.stdout.write(f'📊 Updated {speakers_updated} speaker records\n')

    def update_speaker_current_parties(self, dry_run):
        """Update speaker current_party relationships"""
        self.stdout.write('🔍 Step 2: Updating speaker current_party relationships...')
        
        updated_count = 0
        
        for speaker in Speaker.objects.all():
            current_party_name = speaker.get_current_party_name()
            
            if current_party_name == '정당정보없음':
                if speaker.current_party:
                    if not dry_run:
                        speaker.current_party = None
                        speaker.save()
                    updated_count += 1
                    self.stdout.write(f'  🔄 Cleared party for {speaker.naas_nm}')
                continue
            
            # Get or create the party
            if not dry_run:
                party, created = Party.objects.get_or_create(
                    name=current_party_name,
                    defaults={
                        'description': f'{current_party_name} - 국회의원 데이터에서 추출',
                        'assembly_era': 22  # Default to current assembly
                    }
                )
                
                if speaker.current_party != party:
                    speaker.current_party = party
                    speaker.save()
                    updated_count += 1
                    self.stdout.write(f'  ✅ Updated {speaker.naas_nm} -> {current_party_name}')
            else:
                # Just check if it would be updated
                try:
                    party = Party.objects.get(name=current_party_name)
                    if speaker.current_party != party:
                        updated_count += 1
                        self.stdout.write(f'  🔄 Would update {speaker.naas_nm} -> {current_party_name}')
                except Party.DoesNotExist:
                    updated_count += 1
                    self.stdout.write(f'  ✨ Would create party and update {speaker.naas_nm} -> {current_party_name}')
        
        self.stdout.write(f'📊 Updated {updated_count} speaker-party relationships\n')

    def consolidate_duplicate_parties(self, dry_run):
        """Remove duplicate Party records and consolidate data"""
        self.stdout.write('🔍 Step 3: Consolidating duplicate Party records...')
        
        # Find parties with the same name
        party_names = Party.objects.values('name').annotate(
            count=Count('id')
        ).filter(count__gt=1)
        
        consolidated_count = 0
        
        for party_info in party_names:
            party_name = party_info['name']
            duplicates = Party.objects.filter(name=party_name).order_by('id')
            
            if duplicates.count() <= 1:
                continue
            
            self.stdout.write(f'  📋 Found {duplicates.count()} duplicates for "{party_name}"')
            
            # Keep the first one (lowest ID) and merge others into it
            primary_party = duplicates.first()
            duplicate_parties = duplicates[1:]
            
            for duplicate in duplicate_parties:
                if not dry_run:
                    # Update all speakers pointing to duplicate party
                    Speaker.objects.filter(current_party=duplicate).update(current_party=primary_party)
                    
                    # Delete the duplicate
                    duplicate.delete()
                    
                consolidated_count += 1
                self.stdout.write(f'    🗑️  Removed duplicate party ID {duplicate.id}')
        
        self.stdout.write(f'📊 Consolidated {consolidated_count} duplicate parties\n')

    def show_party_statistics(self):
        """Show final party statistics"""
        self.stdout.write('📈 Final Party Statistics:')
        self.stdout.write('=' * 50)
        
        parties_with_members = Party.objects.annotate(
            member_count=Count('current_members')
        ).filter(member_count__gt=0).order_by('-member_count')
        
        for party in parties_with_members:
            self.stdout.write(f'🏛️  {party.name}: {party.member_count} members')
        
        # Show parties without members
        parties_without_members = Party.objects.annotate(
            member_count=Count('current_members')
        ).filter(member_count=0)
        
        if parties_without_members.exists():
            self.stdout.write(f'\n⚠️  {parties_without_members.count()} parties have no current members')
        
        self.stdout.write(f'\n📊 Total parties: {Party.objects.count()}')
        self.stdout.write(f'📊 Total speakers: {Speaker.objects.count()}')
