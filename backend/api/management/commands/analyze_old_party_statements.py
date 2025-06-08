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
            help='Show actual statement content',
        )
        parser.add_argument(
            '--sentiment-only',
            action='store_true',
            help='Only show statements with sentiment analysis',
        )
        parser.add_argument(
            '--list-all-members',
            action='store_true',
            help='List ALL members of historical parties with detailed info',
        )
        parser.add_argument(
            '--show-member-details',
            action='store_true',
            help='Show detailed member information (electoral district, assembly era, etc.)',
        )

    def handle(self, *args, **options):
        party_filter = options.get('party')
        show_statements = options.get('show_statements', False)
        sentiment_only = options.get('sentiment_only', False)
        list_all_members = options.get('list_all_members', False)
        show_member_details = options.get('show_member_details', False)

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
        all_sentiments = 0

        if list_all_members:
            self.list_all_historical_party_members(old_parties, show_member_details)
            return  # Exit early

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
                all_sentiments += avg_sentiment * statement_count if avg_sentiment else 0

            self.stdout.write('')

        # Overall summary
        self.stdout.write(self.style.SUCCESS('📊 전체 요약:'))
        self.stdout.write(f'   총 의원 수: {total_speakers}명')
        self.stdout.write(f'   총 발언 수: {total_statements}개')

        if total_statements > 0:
            overall_sentiment = all_sentiments / total_statements
            self.stdout.write(f'   전체 평균 감정 점수: {overall_sentiment:.3f}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('💡 사용법:'))
        self.stdout.write('   특정 정당만 보기: --party "한나라당"')
        self.stdout.write('   발언 내용 보기: --show-statements')
        self.stdout.write('   감정 분석된 것만: --sentiment-only')
        self.stdout.write('   모든 역사적 정당 의원 목록: --list-all-members')
        self.stdout.write('   의원 상세 정보 포함: --list-all-members --show-member-details')

    def list_all_historical_party_members(self, old_parties, show_details=False):
        """List ALL members of historical parties with comprehensive details"""
        self.stdout.write(self.style.SUCCESS('👥 역사적 정당에 속한 모든 의원 목록'))
        self.stdout.write('=' * 100)
        self.stdout.write('')

        total_affected_speakers = 0
        total_statements_affected = 0

        # Current parties for comparison
        current_parties = {
            '더불어민주당', '국민의힘', '개혁신당', '새로운미래', '진보당',
            '사회민주당', '무소속', '조국혁신당', '새누리당'
        }

        for party_name in old_parties:
            self.stdout.write(self.style.WARNING(f'🏛️  정당: {party_name}'))
            self.stdout.write('-' * 80)

            # Find ALL speakers with this party in their history
            speakers = Speaker.objects.filter(plpt_nm__icontains=party_name)

            if not speakers.exists():
                self.stdout.write(f'   ❌ {party_name}: 해당 정당 의원 없음')
                self.stdout.write('')
                continue

            self.stdout.write(f'   👥 총 {speakers.count()}명의 의원이 발견됨')
            self.stdout.write('')

            party_statements = 0
            current_22nd_members = 0

            for i, speaker in enumerate(speakers, 1):
                # Get statement count
                statement_count = Statement.objects.filter(speaker=speaker).count()
                party_statements += statement_count

                # Check if they're in 22nd assembly
                is_22nd = '22' in speaker.gtelt_eraco
                if is_22nd:
                    current_22nd_members += 1

                # Get their actual current party
                current_party = speaker.get_current_party_name()
                is_current_party = current_party in current_parties

                # Get full party history
                party_history = speaker.get_party_list()

                # Basic info
                self.stdout.write(f'   {i:2d}. 👤 {speaker.naas_nm} (코드: {speaker.naas_cd})')

                if show_details:
                    self.stdout.write(f'       🗳️  당선대수: {speaker.gtelt_eraco}')
                    self.stdout.write(f'       🏛️  선거구: {speaker.elecd_nm or "정보없음"}')
                    self.stdout.write(f'       📋 전체 정당 이력: {speaker.plpt_nm}')
                    self.stdout.write(f'       🎯 현재 정당: {current_party}')
                    self.stdout.write(f'       📊 발언 수: {statement_count}개')

                    # Flag problematic assignments
                    if is_22nd and party_name in ['대한독립촉성국민회', '민주정의당', '민주자유당']:
                        self.stdout.write(f'       ⚠️  문제: 22대 의원이 역사적 정당에 배정됨!')

                    if not is_current_party:
                        self.stdout.write(f'       ⚠️  문제: 알 수 없는 현재 정당 "{current_party}"')

                    self.stdout.write('')
                else:
                    # Compact format
                    status_flags = []
                    if is_22nd:
                        status_flags.append('22대')
                    if party_name in ['대한독립촉성국민회', '민주정의당', '민주자유당'] and is_22nd:
                        status_flags.append('⚠️문제')
                    if not is_current_party:
                        status_flags.append('⚠️알수없는정당')

                    status = f" [{', '.join(status_flags)}]" if status_flags else ""
                    self.stdout.write(f'       현재: {current_party} | 발언: {statement_count}개{status}')

            total_affected_speakers += speakers.count()
            total_statements_affected += party_statements

            self.stdout.write('')
            self.stdout.write(f'   📊 {party_name} 요약:')
            self.stdout.write(f'       총 의원 수: {speakers.count()}명')
            self.stdout.write(f'       22대 의원 수: {current_22nd_members}명')
            self.stdout.write(f'       총 발언 수: {party_statements}개')

            if party_name in ['대한독립촉성국민회', '민주정의당', '민주자유당']:
                self.stdout.write(f'       ⚠️  데이터 이상: 역사적 정당에 현재 의원 {current_22nd_members}명 배정됨')

            self.stdout.write('')

        # Overall summary
        self.stdout.write('=' * 100)
        self.stdout.write(self.style.SUCCESS('📈 전체 요약'))
        self.stdout.write(f'   총 영향받은 의원: {total_affected_speakers}명')
        self.stdout.write(f'   총 영향받은 발언: {total_statements_affected}개')
        self.stdout.write('')
        self.stdout.write(self.style.ERROR('⚠️  주요 문제점:'))

        # Check for specific problematic cases
        independence_members = Speaker.objects.filter(plpt_nm__icontains='대한독립촉성국민회').count()
        if independence_members > 0:
            self.stdout.write(f'   • {independence_members}명이 일제강점기 독립운동 단체에 배정됨')

        min_justice_members = Speaker.objects.filter(plpt_nm__icontains='민주정의당').count()
        if min_justice_members > 0:
            self.stdout.write(f'   • {min_justice_members}명이 1980년대 정당에 배정됨')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🔧 권장 해결책:'))
        self.stdout.write('   1. python manage.py cleanup_old_parties --dry-run (문제 확인)')
        self.stdout.write('   2. python manage.py cleanup_old_parties (데이터 정리)')
        self.stdout.write('   3. python manage.py verify_22nd_assembly_members (검증)')