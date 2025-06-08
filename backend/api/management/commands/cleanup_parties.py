
from django.core.management.base import BaseCommand
from api.models import Party


class Command(BaseCommand):
    help = 'Clean up parties and mark only current 22nd assembly parties'

    def handle(self, *args, **options):
        # Current 22nd assembly parties
        current_22nd_parties = [
            '더불어민주당',
            '국민의힘', 
            '조국혁신당',
            '진보당',
            '개혁신당',
            '기본소득당',  # You wrote 기복소득당 but I assume you meant 기본소득당
            '사회민주당',
            '무소속'
        ]
        
        self.stdout.write('🔄 Updating party assembly eras...')
        
        # First, set all parties to assembly_era = 0
        Party.objects.all().update(assembly_era=0)
        self.stdout.write('📝 Set all parties to assembly_era = 0')
        
        # Then, update current 22nd assembly parties
        updated_count = 0
        for party_name in current_22nd_parties:
            parties = Party.objects.filter(name=party_name)
            if parties.exists():
                parties.update(assembly_era=22)
                updated_count += parties.count()
                self.stdout.write(f'✅ Updated {party_name} to 22nd assembly')
            else:
                # Create the party if it doesn't exist
                Party.objects.create(
                    name=party_name,
                    assembly_era=22,
                    description=f'{party_name} - 제22대 국회'
                )
                updated_count += 1
                self.stdout.write(f'✨ Created {party_name} as 22nd assembly party')
        
        # Show summary
        total_parties = Party.objects.count()
        current_parties = Party.objects.filter(assembly_era=22).count()
        historical_parties = Party.objects.filter(assembly_era=0).count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Party cleanup completed!\n'
                f'   📊 Total parties: {total_parties}\n'
                f'   🏛️  22nd assembly parties: {current_parties}\n'
                f'   📚 Historical parties: {historical_parties}'
            )
        )
