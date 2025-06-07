
from django.core.management.base import BaseCommand
from api.models import Party, Speaker
from django.db.models import Q


class Command(BaseCommand):
    help = 'Update assembly eras for existing parties'

    def handle(self, *args, **options):
        self.stdout.write('🔄 Updating party assembly eras...')
        
        # Current 22nd assembly parties (from nepjpxkkabqiqpbvk API)
        current_parties = [
            '더불어민주당', '국민의힘', '조국혁신당', '개혁신당', 
            '진보당', '기본소득당', '자유통일당', '새로운미래'
        ]
        
        for party in Party.objects.all():
            # Check if this party has speakers with 22대 in their gtelt_eraco
            current_speakers = Speaker.objects.filter(
                Q(plpt_nm__icontains=party.name) &
                (Q(gtelt_eraco__icontains='22') | Q(gtelt_eraco__icontains='제22대'))
            )
            
            if current_speakers.exists() or any(cp in party.name for cp in current_parties):
                party.assembly_era = 22
                self.stdout.write(f'✅ Set {party.name} to 22nd assembly')
            else:
                # For historical parties, try to detect era from speakers
                all_speakers = Speaker.objects.filter(plpt_nm__icontains=party.name)
                detected_era = 21  # Default to 21 for historical parties
                
                for speaker in all_speakers:
                    era_text = speaker.gtelt_eraco or ""
                    import re
                    era_match = re.search(r'(\d+)대', era_text)
                    if era_match:
                        era = int(era_match.group(1))
                        if era > detected_era:
                            detected_era = era
                
                party.assembly_era = detected_era
                self.stdout.write(f'📊 Set {party.name} to {detected_era}th assembly')
            
            party.save()
        
        self.stdout.write(
            self.style.SUCCESS('✅ Party assembly eras updated successfully!')
        )
