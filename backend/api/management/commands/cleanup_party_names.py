
from django.core.management.base import BaseCommand
from api.models import Speaker, Party, SpeakerPartyHistory
from django.db import transaction


class Command(BaseCommand):
    help = 'Clean up party names by using only the rightmost party from slash-separated lists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually making changes',
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show statistics about party names',
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
        
        speakers = Speaker.objects.all()
        updated_count = 0
        simplified_count = 0
        
        self.stdout.write(f'📊 Processing {speakers.count()} speakers...')
        
        # Show statistics if requested
        if show_stats:
            self.show_party_statistics()
            return
        
        with transaction.atomic():
            for speaker in speakers:
                try:
                    original_plpt_nm = speaker.plpt_nm
                    party_list = speaker.get_party_list()
                    
                    if not party_list:
                        continue
                    
                    # Get the most recent (rightmost) party
                    most_recent_party = party_list[-1].strip()
                    
                    # Only update if there are multiple parties (contains slashes)
                    if len(party_list) > 1:
                        simplified_count += 1
                        self.stdout.write(f'📝 Simplifying {speaker.naas_nm}: {original_plpt_nm} → {most_recent_party}')
                        
                        if not dry_run:
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
                    f'   Would simplify: {simplified_count} speakers\n'
                    f'   Would update: {updated_count} speakers'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ CLEANUP COMPLETE:\n'
                    f'   Simplified: {simplified_count} speakers\n'
                    f'   Updated: {updated_count} speakers'
                )
            )
    
    def show_party_statistics(self):
        """Show statistics about party names in the database"""
        self.stdout.write('\n📊 PARTY STATISTICS:')
        
        # Get unique party names
        unique_parties = set()
        slash_parties = []
        
        speakers = Speaker.objects.all()
        for speaker in speakers:
            if speaker.plpt_nm:
                unique_parties.add(speaker.plpt_nm)
                if '/' in speaker.plpt_nm:
                    slash_parties.append(speaker.plpt_nm)
        
        self.stdout.write(f'📈 Total unique party entries: {len(unique_parties)}')
        self.stdout.write(f'📈 Entries with slashes: {len(slash_parties)}')
        
        # Show some examples
        self.stdout.write('\n🔍 Examples of slash-separated parties:')
        for party in sorted(set(slash_parties))[:10]:
            count = Speaker.objects.filter(plpt_nm=party).count()
            self.stdout.write(f'   {party} ({count} speakers)')
        
        # Show party distribution
        from django.db.models import Count
        party_counts = Speaker.objects.values('plpt_nm').annotate(
            count=Count('naas_cd')
        ).order_by('-count')[:20]
        
        self.stdout.write('\n📊 Top 20 party entries by speaker count:')
        for item in party_counts:
            self.stdout.write(f'   {item["plpt_nm"]}: {item["count"]} speakers')
