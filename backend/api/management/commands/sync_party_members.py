
from django.core.management.base import BaseCommand
from api.models import Party, Speaker, SpeakerPartyHistory
from django.db.models import Count
from django.db import transaction


class Command(BaseCommand):
    help = 'Synchronize party and member relationships and create missing parties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-missing-parties',
            action='store_true',
            help=
            'Create Party records for parties that have members but no Party record',
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show detailed statistics about parties and members',
        )

    def handle(self, *args, **options):
        create_missing = options['create_missing_parties']
        show_stats = options['show_stats']

        self.stdout.write(
            self.style.SUCCESS(
                '🔄 Synchronizing party and member relationships...'))

        # Get all unique party names from speakers (including full history strings)
        speaker_parties = Speaker.objects.exclude(plpt_nm__isnull=True).exclude(plpt_nm='').values('plpt_nm').annotate(
            member_count=Count('naas_cd')).order_by('plpt_nm')

        self.stdout.write(
            f'📊 Found {len(speaker_parties)} unique party strings in speaker data')

        created_parties = 0
        updated_speakers = 0

        with transaction.atomic():
            # Process each speaker to handle party history and current party
            for speaker in Speaker.objects.exclude(plpt_nm__isnull=True).exclude(plpt_nm=''):
                if not speaker.plpt_nm:
                    continue
                    
                # Split party history by '/'
                party_names = [name.strip() for name in speaker.plpt_nm.split('/') if name.strip()]
                
                if not party_names:
                    continue
                
                # The rightmost party is the current party
                current_party_name = party_names[-1]
                
                # Create or get current party (assume 22nd assembly for new parties)
                current_party, created = Party.objects.get_or_create(
                    name=current_party_name,
                    defaults={
                        'description': f'{current_party_name} - 제22대 국회',
                        'assembly_era': 22
                    }
                )
                
                if created and create_missing:
                    created_parties += 1
                    self.stdout.write(f'✅ Created party: {current_party_name}')
                
                # Update speaker's current party
                if speaker.current_party != current_party:
                    speaker.current_party = current_party
                    speaker.save()
                    updated_speakers += 1
                
                # Clear existing party history for this speaker
                SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                
                # Create party history entries for all parties
                for order, party_name in enumerate(party_names):
                    # Create or get each party in the history
                    party, created = Party.objects.get_or_create(
                        name=party_name,
                        defaults={
                            'description': f'{party_name} - 제22대 국회',
                            'assembly_era': 22
                        }
                    )
                    
                    if created and create_missing:
                        created_parties += 1
                        self.stdout.write(f'✅ Created party: {party_name}')
                    
                    # Create party history entry
                    is_current = (order == len(party_names) - 1)  # Last party is current
                    SpeakerPartyHistory.objects.create(
                        speaker=speaker,
                        party=party,
                        order=order,
                        is_current=is_current
                    )

            # Also create parties from unique party names for completeness
            all_unique_parties = set()
            for speaker_party in speaker_parties:
                party_name = speaker_party['plpt_nm']
                if party_name:
                    # Split and add all individual party names
                    party_names = [name.strip() for name in party_name.split('/') if name.strip()]
                    all_unique_parties.update(party_names)
            
            # Create any remaining missing parties
            for party_name in all_unique_parties:
                party, created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={
                        'description': f'{party_name} - 제22대 국회',
                        'assembly_era': 22
                    }
                )
                
                if created and create_missing:
                    created_parties += 1
                    self.stdout.write(f'✅ Created party: {party_name}')

        if create_missing:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Created {created_parties} new party records'))
            self.stdout.write(
                self.style.SUCCESS(
                    f'🔄 Updated {updated_speakers} speaker current parties'))

        if show_stats:
            self.stdout.write('\n📈 Party Statistics:')
            self.stdout.write('=' * 50)

            for party in Party.objects.all():
                # Count current members
                current_members = Speaker.objects.filter(current_party=party)
                current_count = current_members.count()
                
                # Count historical members
                historical_count = SpeakerPartyHistory.objects.filter(party=party).values('speaker').distinct().count()

                self.stdout.write(f'🏛️  {party.name}:')
                self.stdout.write(f'   • Current Members: {current_count}')
                self.stdout.write(f'   • Historical Members: {historical_count}')

                if current_count > 0:
                    # Gender distribution of current members
                    male_count = current_members.filter(ntr_div='남').count()
                    female_count = current_members.filter(ntr_div='여').count()

                    self.stdout.write(
                        f'   • Current Gender Split - Male: {male_count}, Female: {female_count}')

                    # Committee distribution of current members
                    committees = current_members.values('cmit_nm').annotate(
                        count=Count('naas_cd')).order_by('-count')[:3]

                    if committees:
                        self.stdout.write('   • Top Committees (Current Members):')
                        for committee in committees:
                            if committee['cmit_nm']:
                                self.stdout.write(
                                    f'     - {committee["cmit_nm"]}: {committee["count"]} members'
                                )

                self.stdout.write('')

        self.stdout.write(
            self.style.SUCCESS('✅ Party-member synchronization completed!'))
