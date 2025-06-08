
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement
from django.db.models import Count, Avg, Q
from collections import defaultdict

class Command(BaseCommand):
    help = 'Analyze statements and sentiment from speakers with old party names'

    def add_arguments(self, parser):
        parser.add_argument(
            '--party',
            type=str,
            help='Filter by specific party name',
        )
        parser.add_argument(
            '--show-statements',
            action='store_true',
            help='Show actual statement texts (first 200 chars)',
        )
        parser.add_argument(
            '--sentiment-only',
            action='store_true',
            help='Only show statements with sentiment scores',
        )

    def handle(self, *args, **options):
        party_filter = options.get('party')
        show_statements = options.get('show_statements', False)
        sentiment_only = options.get('sentiment_only', False)
        
        # Define the old party names we're investigating
        old_parties = [
            '대한독립촉성국민회', '한나라당', '민주자유당', '민주정의당', '정보없음'
        ]
        
        if party_filter:
            old_parties = [party_filter]
        
        self.stdout.write(self.style.SUCCESS('🔍 Analyzing statements from old party members...'))
        self.stdout.write('')
        
        total_statements = 0
        total_speakers = 0
        
        for party_name in old_parties:
            self.stdout.write(self.style.WARNING(f'📋 분석 중: {party_name}'))
            self.stdout.write('-' * 80)
            
            # Find speakers with this party name
            speakers = Speaker.objects.filter(plpt_nm__icontains=party_name)
            
            if not speakers.exists():
                self.stdout.write(f'   ❌ {party_name}: 해당 정당 의원 없음')
                self.stdout.write('')
                continue
            
            party_statements = Statement.objects.filter(speaker__in=speakers)
            
            if sentiment_only:
                party_statements = party_statements.filter(sentiment_score__isnull=False)
            
            statement_count = party_statements.count()
            speaker_count = speakers.count()
            
            self.stdout.write(f'   👥 의원 수: {speaker_count}명')
            self.stdout.write(f'   💬 발언 수: {statement_count}개')
            
            if statement_count > 0:
                # Sentiment analysis
                sentiment_stats = party_statements.aggregate(
                    avg_sentiment=Avg('sentiment_score'),
                    total_with_sentiment=Count('id', filter=Q(sentiment_score__isnull=False))
                )
                
                avg_sentiment = sentiment_stats['avg_sentiment']
                total_with_sentiment = sentiment_stats['total_with_sentiment']
                
                if avg_sentiment is not None:
                    self.stdout.write(f'   📊 감정 점수 평균: {avg_sentiment:.3f}')
                    self.stdout.write(f'   📈 감정 분석된 발언: {total_with_sentiment}개')
                    
                    # Sentiment distribution
                    positive = party_statements.filter(sentiment_score__gt=0.3).count()
                    negative = party_statements.filter(sentiment_score__lt=-0.3).count()
                    neutral = total_with_sentiment - positive - negative
                    
                    self.stdout.write(f'   ✅ 긍정: {positive}개')
                    self.stdout.write(f'   ⚖️  중립: {neutral}개') 
                    self.stdout.write(f'   ❌ 부정: {negative}개')
                else:
                    self.stdout.write('   📊 감정 분석된 발언 없음')
                
                # Show top speakers by statement count
                top_speakers = speakers.annotate(
                    statement_count=Count('statements'),
                    avg_sentiment=Avg('statements__sentiment_score')
                ).filter(statement_count__gt=0).order_by('-statement_count')[:5]
                
                if top_speakers:
                    self.stdout.write('   🏆 주요 발언자:')
                    for speaker in top_speakers:
                        sentiment_info = f'(평균 감정: {speaker.avg_sentiment:.3f})' if speaker.avg_sentiment else '(감정분석 없음)'
                        self.stdout.write(f'     - {speaker.naas_nm}: {speaker.statement_count}개 발언 {sentiment_info}')
                
                # Show recent statements if requested
                if show_statements:
                    self.stdout.write('   📝 최근 발언 예시:')
                    recent_statements = party_statements.select_related('speaker').order_by('-created_at')[:3]
                    
                    for stmt in recent_statements:
                        sentiment_info = f'(감정: {stmt.sentiment_score:.3f})' if stmt.sentiment_score else '(감정분석 없음)'
                        text_preview = stmt.text[:200] + '...' if len(stmt.text) > 200 else stmt.text
                        self.stdout.write(f'     - {stmt.speaker.naas_nm}: "{text_preview}" {sentiment_info}')
                
                total_statements += statement_count
                total_speakers += speaker_count
            
            self.stdout.write('')
        
        # Overall summary
        self.stdout.write(self.style.SUCCESS('📊 전체 요약:'))
        self.stdout.write(f'   총 의원 수: {total_speakers}명')
        self.stdout.write(f'   총 발언 수: {total_statements}개')
        
        if total_statements > 0:
            # Get overall sentiment for all old party statements
            all_old_party_statements = Statement.objects.filter(
                speaker__plpt_nm__icontains=old_parties[0]
            )
            for party in old_parties[1:]:
                all_old_party_statements = all_old_party_statements | Statement.objects.filter(
                    speaker__plpt_nm__icontains=party
                )
            
            overall_sentiment = all_old_party_statements.aggregate(
                avg_sentiment=Avg('sentiment_score')
            )['avg_sentiment']
            
            if overall_sentiment:
                self.stdout.write(f'   전체 평균 감정 점수: {overall_sentiment:.3f}')
        
        self.stdout.write('')
        self.stdout.write('💡 사용법:')
        self.stdout.write('   특정 정당만 보기: --party "한나라당"')
        self.stdout.write('   발언 내용 보기: --show-statements')
        self.stdout.write('   감정 분석된 것만: --sentiment-only')
