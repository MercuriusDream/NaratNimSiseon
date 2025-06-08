from django.core.management.base import BaseCommand
from api.models import Speaker, Party, SpeakerPartyHistory
from django.db import transaction


class Command(BaseCommand):
    help = 'Fix Democratic party name variations to use only the rightmost party name'

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

        updated_count = 0

        with transaction.atomic():
            # Find speakers with Democratic party slash-separated variations
            democratic_slash_patterns = [
                '민주통합당/더불어민주당',
                '새정치민주연합/더불어민주당', 
                '민주통합당/더불어민주당/더불어민주당/더불어민주당',
                '새정치민주연합/더불어민주당/더불어민주당',
            ]

            for pattern in democratic_slash_patterns:
                speakers = Speaker.objects.filter(plpt_nm__exact=pattern)

                for speaker in speakers:
                    party_list = speaker.get_party_list()
                    if party_list:
                        # Use the rightmost (most recent) party
                        rightmost_party = party_list[-1].strip()

                        self.stdout.write(f'🔄 Updating {speaker.naas_nm}: {speaker.plpt_nm} → {rightmost_party}')

                        if not dry_run:
                            # Get or create the target party
                            target_party, created = Party.objects.get_or_create(
                                name=rightmost_party,
                                defaults={
                                    'description': f'{rightmost_party} - 제22대 국회',
                                    'assembly_era': 22
                                }
                            )
                            if created:
                                self.stdout.write(f'✨ Created target party: {rightmost_party}')

                            # Update speaker
                            speaker.plpt_nm = rightmost_party
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

        # NOTE: We deliberately do NOT change 더불어민주연합 to 더불어민주당
        # as they are different parties and should remain distinct

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'🔍 Would update {updated_count} speakers')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Updated {updated_count} speakers to use rightmost party name')
            )

        self.stdout.write(
            self.style.SUCCESS('📝 Note: 더불어민주연합 speakers were left unchanged as requested')
        )