
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement
from django.db.models import Count, Avg
from collections import defaultdict

class Command(BaseCommand):
    help = 'Show speakers who have old party names in their plpt_nm field'

    def handle(self, *args, **options):
        # Define the old party names we're looking for
        old_parties = [
            '민주정의당', '민주자유당', '대한독립촉성국민회', '한나라당',
            '신민당', '바른정당', '한국당', '정보없음'
        ]
        
        self.stdout.write(self.style.SUCCESS('🔍 Searching for speakers with old party names...'))
        self.stdout.write('')
        
        total_found = 0
        
        for party_name in old_parties:
            # Find speakers who have this party name in their plpt_nm field
            speakers = Speaker.objects.filter(plpt_nm__icontains=party_name)
            
            if speakers.exists():
                self.stdout.write(self.style.WARNING(f'📋 찾은 정당: {party_name} ({speakers.count()}명)'))
                self.stdout.write('-' * 80)
                
                for speaker in speakers[:10]:  # Limit to first 10 for readability
                    # Get statement count for this speaker
                    statement_count = Statement.objects.filter(speaker=speaker).count()
                    
                    # Show full party history
                    party_list = speaker.get_party_list()
                    
                    self.stdout.write(f'  👤 {speaker.naas_nm} (코드: {speaker.naas_cd})')
                    self.stdout.write(f'     당선대수: {speaker.gtelt_eraco}')
                    self.stdout.write(f'     전체 정당 이력: {speaker.plpt_nm}')
                    self.stdout.write(f'     정당 목록: {party_list}')
                    self.stdout.write(f'     현재 정당: {speaker.get_current_party_name()}')
                    self.stdout.write(f'     발언 수: {statement_count}')
                    self.stdout.write('')
                
                if speakers.count() > 10:
                    self.stdout.write(f'     ... 그리고 {speakers.count() - 10}명 더')
                    self.stdout.write('')
                
                total_found += speakers.count()
            else:
                self.stdout.write(f'❌ {party_name}: 찾은 의원 없음')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'📊 총 발견된 의원 수: {total_found}명'))
        
        # Show some statistics about assembly eras
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('📈 대수별 통계:'))
        
        # Get era statistics
        era_stats = Speaker.objects.values('gtelt_eraco').annotate(
            count=Count('naas_cd')
        ).order_by('gtelt_eraco')
        
        for era in era_stats:
            self.stdout.write(f'  {era["gtelt_eraco"]}: {era["count"]}명')
        
        # Show 22nd Assembly specific info
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🏛️  22대 국회 의원 정보:'))
        
        assembly_22_speakers = Speaker.objects.filter(
            gtelt_eraco__icontains='22'
        )
        
        self.stdout.write(f'  총 22대 의원: {assembly_22_speakers.count()}명')
        
        # Show party distribution for 22nd Assembly
        party_stats_22 = defaultdict(int)
        for speaker in assembly_22_speakers:
            current_party = speaker.get_current_party_name()
            party_stats_22[current_party] += 1
        
        self.stdout.write('  22대 정당별 분포:')
        for party, count in sorted(party_stats_22.items(), key=lambda x: x[1], reverse=True):
            if count > 5:  # Only show parties with more than 5 members
                self.stdout.write(f'    {party}: {count}명')
