from django.core.management.base import BaseCommand
from api.models import Party, Speaker
from django.db.models import Count


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

        # Get all unique party names from speakers
        speaker_parties = Speaker.objects.values('plpt_nm').annotate(
            member_count=Count('naas_cd')).order_by('plpt_nm')

        self.stdout.write(
            f'📊 Found {len(speaker_parties)} unique parties in speaker data')

        created_parties = 0

        for speaker_party in speaker_parties:
            party_name = speaker_party['plpt_nm']
            member_count = speaker_party['member_count']

            if party_name:  # Skip empty party names
                party, created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={'description': f'정당 - {member_count}명의 의원'})

                if created and create_missing:
                    created_parties += 1
                    self.stdout.write(f'✅ Created party: {party_name}')
                elif not created:
                    self.stdout.write(f'🔄 Party already exists: {party_name}')

        if create_missing:
            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Created {created_parties} new party records'))

        if show_stats:
            self.stdout.write('\n📈 Party Statistics:')
            self.stdout.write('=' * 50)

            for party in Party.objects.all():
                members = Speaker.objects.filter(plpt_nm=party.name)
                member_count = members.count()

                self.stdout.write(f'🏛️  {party.name}:')
                self.stdout.write(f'   • Total Members: {member_count}')

                if member_count > 0:
                    # Gender distribution
                    male_count = members.filter(ntr_div='남').count()
                    female_count = members.filter(ntr_div='여').count()

                    self.stdout.write(
                        f'   • Male: {male_count}, Female: {female_count}')

                    # Committee distribution
                    committees = members.values('cmit_nm').annotate(
                        count=Count('naas_cd')).order_by('-count')[:3]

                    if committees:
                        self.stdout.write('   • Top Committees:')
                        for committee in committees:
                            if committee['cmit_nm']:
                                self.stdout.write(
                                    f'     - {committee["cmit_nm"]}: {committee["count"]} members'
                                )

                self.stdout.write('')

        self.stdout.write(
            self.style.SUCCESS('✅ Party-member synchronization completed!'))
