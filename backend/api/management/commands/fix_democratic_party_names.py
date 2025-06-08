
from django.core.management.base import BaseCommand
from api.models import Speaker, Party, SpeakerPartyHistory
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix Democratic party name variations to use only 더불어민주당'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN MODE - No changes will be made')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🧹 Fixing Democratic party name variations...')
        )
        
        # Find speakers with Democratic party variations
        democratic_variations = [
            '민주통합당/더불어민주당/더불어민주당/더불어민주당',
            '더불어민주연합',
            '민주통합당/더불어민주당',
            '새정치민주연합/더불어민주당',
            '민주통합당',
            '새정치민주연합'
        ]
        
        updated_count = 0
        target_party_name = '더불어민주당'
        
        # Get or create the target party
        if not dry_run:
            target_party, created = Party.objects.get_or_create(
                name=target_party_name,
                defaults={
                    'description': '더불어민주당 - 제22대 국회',
                    'assembly_era': 22
                }
            )
            if created:
                self.stdout.write(f'✨ Created target party: {target_party_name}')
        
        with transaction.atomic():
            for variation in democratic_variations:
                speakers = Speaker.objects.filter(plpt_nm__icontains=variation)
                
                for speaker in speakers:
                    self.stdout.write(f'🔄 Updating {speaker.naas_nm}: {speaker.plpt_nm} → {target_party_name}')
                    
                    if not dry_run:
                        # Update speaker
                        speaker.plpt_nm = target_party_name
                        speaker.current_party = target_party
                        speaker.save()
                        
                        # Update party history
                        SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=target_party,
                            order=0,
                            is_current=True
                        )
                        
                        updated_count += 1
        
        # Also handle speakers with multiple party history where the last one should be 더불어민주당
        speakers_with_multiple = Speaker.objects.filter(plpt_nm__icontains='/')
        
        for speaker in speakers_with_multiple:
            party_list = speaker.get_party_list()
            if party_list:
                last_party = party_list[-1].strip()
                
                # Check if the last party is a Democratic party variation
                if any(dem_name in last_party for dem_name in ['민주', '더불어']):
                    self.stdout.write(f'🔄 Simplifying {speaker.naas_nm}: {speaker.plpt_nm} → {target_party_name}')
                    
                    if not dry_run:
                        speaker.plpt_nm = target_party_name
                        speaker.current_party = target_party
                        speaker.save()
                        
                        # Update party history
                        SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=target_party,
                            order=0,
                            is_current=True
                        )
                        
                        updated_count += 1
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'🔍 Would update {updated_count} speakers')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Updated {updated_count} speakers to use {target_party_name}')
            )
