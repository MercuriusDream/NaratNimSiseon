
from django.core.management.base import BaseCommand
from api.models import Speaker, Party, SpeakerPartyHistory
from django.db import transaction


class Command(BaseCommand):
    help = 'Clean up party names to use only the most recent party and fix incorrect party mappings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually making changes',
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show statistics about party mappings',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        show_stats = options['show_stats']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🧹 Starting party name cleanup...')
        )
        
        # Party name mappings for incorrect names
        party_mappings = {
            '더불어민주연합': '더불어민주당',
            '민주통합당': '더불어민주당',  # Historical party that became 더불어민주당
            '새정치민주연합': '더불어민주당',  # Historical party that became 더불어민주당
        }
        
        speakers = Speaker.objects.all()
        updated_count = 0
        cleaned_count = 0
        
        self.stdout.write(f'📊 Processing {speakers.count()} speakers...')
        
        with transaction.atomic():
            for speaker in speakers:
                try:
                    original_plpt_nm = speaker.plpt_nm
                    party_list = speaker.get_party_list()
                    
                    if not party_list:
                        continue
                    
                    # Get the most recent (rightmost) party
                    most_recent_party = party_list[-1].strip()
                    
                    # Apply party mappings if needed
                    if most_recent_party in party_mappings:
                        most_recent_party = party_mappings[most_recent_party]
                        cleaned_count += 1
                        self.stdout.write(f'🔄 Mapping {party_list[-1]} → {most_recent_party} for {speaker.naas_nm}')
                    
                    # Check if we need to update
                    needs_update = False
                    
                    # Case 1: Multiple parties in history, use only the most recent
                    if len(party_list) > 1:
                        needs_update = True
                        self.stdout.write(f'📝 Simplifying {speaker.naas_nm}: {original_plpt_nm} → {most_recent_party}')
                    
                    # Case 2: Single party but needs mapping
                    elif len(party_list) == 1 and party_list[0].strip() in party_mappings:
                        needs_update = True
                        self.stdout.write(f'🔄 Updating {speaker.naas_nm}: {original_plpt_nm} → {most_recent_party}')
                    
                    if needs_update and not dry_run:
                        # Update the speaker's party name to only the most recent
                        speaker.plpt_nm = most_recent_party
                        
                        # Get or create the party object
                        party, created = Party.objects.get_or_create(
                            name=most_recent_party,
                            defaults={
                                'description': f'{most_recent_party} - 정리됨',
                                'assembly_era': 22  # Current assembly
                            }
                        )
                        
                        if created:
                            self.stdout.write(f'✨ Created party: {most_recent_party}')
                        
                        # Set current party
                        speaker.current_party = party
                        speaker.save()
                        
                        # Clear existing party history and create new simplified one
                        SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=party,
                            order=0,
                            is_current=True
                        )
                        
                        updated_count += 1
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Error processing {speaker.naas_nm}: {e}')
                    )
                    continue
        
        # Show results
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'🔍 DRY RUN COMPLETE:\n'
                    f'   Would update: {updated_count} speakers\n'
                    f'   Would clean mappings: {cleaned_count} speakers'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Cleanup completed!\n'
                    f'   Updated: {updated_count} speakers\n'
                    f'   Cleaned mappings: {cleaned_count} speakers'
                )
            )
        
        if show_stats:
            self.show_party_statistics()
    
    def show_party_statistics(self):
        """Show statistics about current party distribution"""
        self.stdout.write('\n📈 Current Party Statistics:')
        self.stdout.write('=' * 50)
        
        from django.db.models import Count
        
        # Count speakers by current party
        party_stats = Speaker.objects.values('current_party__name').annotate(
            member_count=Count('naas_cd')
        ).order_by('-member_count')
        
        for stat in party_stats:
            party_name = stat['current_party__name'] or '정당정보없음'
            member_count = stat['member_count']
            self.stdout.write(f'🏛️  {party_name}: {member_count} members')
        
        # Count unique party names in plpt_nm field
        unique_parties = set()
        for speaker in Speaker.objects.all():
            if speaker.plpt_nm:
                unique_parties.add(speaker.plpt_nm.strip())
        
        self.stdout.write(f'\n📊 Total unique party names: {len(unique_parties)}')
        self.stdout.write('Current party names:')
        for party in sorted(unique_parties):
            if party:
                self.stdout.write(f'   • {party}')
