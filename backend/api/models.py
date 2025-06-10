from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import pre_save
from django.dispatch import receiver


class Session(models.Model):
    conf_id = models.CharField(max_length=50,
                               primary_key=True,
                               verbose_name=_("회의 ID"))
    era_co = models.CharField(max_length=20,
                              help_text=_("대수"),
                              verbose_name=_("대수"))
    sess = models.CharField(max_length=20,
                            help_text=_("회기"),
                            verbose_name=_("회기"))
    dgr = models.CharField(max_length=20,
                           help_text=_("차수"),
                           verbose_name=_("차수"))
    conf_dt = models.DateField(help_text=_("회의일자"), verbose_name=_("회의일자"))
    conf_knd = models.CharField(max_length=100,
                                help_text=_("회의종류"),
                                verbose_name=_("회의종류"))
    cmit_nm = models.CharField(max_length=100,
                               help_text=_("위원회명"),
                               verbose_name=_("위원회명"))
    conf_plc = models.CharField(max_length=200,
                                blank=True,
                                help_text=_("회의장소"),
                                verbose_name=_("회의장소"))
    title = models.CharField(max_length=500,
                             blank=True,
                             help_text=_("회의 제목"),
                             verbose_name=_("회의 제목"))
    bg_ptm = models.TimeField(null=True,
                              blank=True,
                              help_text=_("시작시간"),
                              verbose_name=_("시작시간"))
    ed_ptm = models.TimeField(null=True,
                              blank=True,
                              help_text=_("종료시간"),
                              verbose_name=_("종료시간"))
    down_url = models.URLField(help_text=_("PDF 다운로드 URL"),
                               verbose_name=_("PDF 다운로드 URL"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-conf_dt', '-bg_ptm']
        verbose_name = _("회의")
        verbose_name_plural = _("회의")

    def __str__(self):
        return f"{self.era_co} {self.sess} {self.dgr} ({self.conf_dt})"


from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.contrib.postgres.fields import JSONField


class Bill(models.Model):
    bill_id = models.CharField(max_length=100,
                               primary_key=True,
                               verbose_name=_("의안 ID"))
    session = models.ForeignKey(Session,
                                on_delete=models.CASCADE,
                                related_name='bills',
                                verbose_name=_("관련 회의"))
    bill_nm = models.CharField(max_length=500,
                               help_text=_("의안명"),
                               verbose_name=_("의안명"))
    bill_no = models.CharField(max_length=100,
                               blank=True,
                               null=True,
                               help_text=_("의안번호"),
                               verbose_name=_("의안번호"))
    proposer = models.CharField(max_length=200,
                                default="정보 없음",
                                null=True,
                                blank=True,
                                help_text=_("제안자/제안위원회"),
                                verbose_name=_("제안자"))
    propose_dt = models.CharField(max_length=50,
                                  blank=True,
                                  help_text=_("제안일자"),
                                  verbose_name=_("제안일자"))
    link_url = models.URLField(blank=True,
                               help_text=_("의안 상세 URL"),
                               verbose_name=_("의안 상세 URL"))
    # Enhanced policy analysis fields
    policy_categories = models.JSONField(default=list,
                                         blank=True,
                                         help_text=_("LLM 분석된 정책 대범주 목록"),
                                         verbose_name=_("정책 카테고리"))
    policy_subcategories = models.JSONField(default=list,
                                           blank=True,
                                           help_text=_("LLM 분석된 정책 소범주 목록"),
                                           verbose_name=_("정책 소범주"))
    key_policy_phrases = models.JSONField(default=list,
                                          blank=True,
                                          help_text=_("핵심 정책 키워드 목록"),
                                          verbose_name=_("핵심 정책 키워드"))
    bill_specific_keywords = models.JSONField(
        default=list,
        blank=True,
        help_text=_("의안별 특화 키워드 목록"),
        verbose_name=_("의안별 특화 키워드"))
    bill_specific_keywords_json = models.JSONField(
        default=list,
        blank=True,
        help_text=_("의안별 특화 키워드 (JSON 형태)"),
        verbose_name=_("의안별 특화 키워드 JSON"))
    category_analysis = models.TextField(blank=True,
                                         help_text=_("카테고리 분석 결과"),
                                         verbose_name=_("카테고리 분석 결과"))
    policy_keywords = models.TextField(blank=True,
                                       help_text=_("정책 키워드 (쉼표 구분)"),
                                       verbose_name=_("정책 키워드"))
    
    # Structured category relationships
    primary_categories = models.ManyToManyField('Category',
                                               through='BillCategoryMapping',
                                               related_name='primary_bills',
                                               verbose_name=_("주요 정책 범주"))
    
    # LLM analysis metadata
    llm_analysis_version = models.CharField(max_length=20,
                                           blank=True,
                                           help_text=_("LLM 분석 버전"),
                                           verbose_name=_("분석 버전"))
    llm_confidence_score = models.FloatField(null=True,
                                            blank=True,
                                            help_text=_("LLM 분석 신뢰도 (0-1)"),
                                            verbose_name=_("분석 신뢰도"))
    policy_impact_score = models.FloatField(null=True,
                                           blank=True,
                                           help_text=_("정책 영향도 점수 (0-10)"),
                                           verbose_name=_("정책 영향도"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("의안")
        verbose_name_plural = _("의안")

    def __str__(self):
        return self.bill_nm

    def get_link_url(self):
        """Generate the proper bill detail URL"""
        if self.bill_id:
            return f"https://likms.assembly.go.kr/bill/billDetail.do?billId={self.bill_id}"
        return ""

    def save(self, *args, **kwargs):
        # Auto-generate link_url if not provided
        if not self.link_url and self.bill_id:
            self.link_url = self.get_link_url()
        super().save(*args, **kwargs)


class Party(models.Model):
    name = models.CharField(max_length=100,
                            unique=True,
                            help_text=_("정당명"),
                            verbose_name=_("정당명"))
    logo_url = models.URLField(blank=True,
                               null=True,
                               help_text=_("정당 로고 이미지 URL"),
                               verbose_name=_("정당 로고 URL"))
    slogan = models.CharField(max_length=255,
                              blank=True,
                              help_text=_("정당 슬로건"),
                              verbose_name=_("정당 슬로건"))
    description = models.TextField(blank=True,
                                   help_text=_("정당 설명"),
                                   verbose_name=_("정당 설명"))
    assembly_era = models.PositiveIntegerField(default=22,
                                               help_text=_("국회 대수 (예: 22)"),
                                               verbose_name=_("국회 대수"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "정당"
        verbose_name_plural = "정당 목록"


class Speaker(models.Model):
    naas_cd = models.CharField(max_length=20,
                               primary_key=True,
                               verbose_name=_("국회의원 코드"))
    naas_nm = models.CharField(max_length=100,
                               help_text=_("국회의원명"),
                               verbose_name=_("국회의원명"))
    naas_ch_nm = models.CharField(max_length=100,
                                  blank=True,
                                  help_text=_("국회의원한자명"),
                                  verbose_name=_("국회의원 한자명"))
    plpt_nm = models.CharField(max_length=500,
                               help_text=_("정당명 (전체 이력)"),
                               verbose_name=_("정당명"))
    current_party = models.ForeignKey('Party',
                                      on_delete=models.SET_NULL,
                                      null=True,
                                      blank=True,
                                      related_name='current_members',
                                      verbose_name=_("현재 정당"))
    party_history = models.ManyToManyField('Party',
                                           through='SpeakerPartyHistory',
                                           related_name='historical_members',
                                           verbose_name=_("정당 이력"))
    elecd_nm = models.CharField(max_length=200,
                                blank=True,
                                null=True,
                                help_text=_("선거구명"),
                                verbose_name=_("선거구명"))
    elecd_div_nm = models.CharField(max_length=100,
                                    blank=True,
                                    null=True,
                                    help_text=_("선거구구분명"),
                                    verbose_name=_("선거구 구분명"))
    cmit_nm = models.TextField(blank=True,
                               null=True,
                               help_text=_("대표위원회명"),
                               verbose_name=_("대표위원회명"))
    blng_cmit_nm = models.TextField(blank=True,
                                    null=True,
                                    help_text=_("소속위원회명"),
                                    verbose_name=_("소속위원회명"))
    rlct_div_nm = models.CharField(max_length=50,
                                   help_text=_("재선구분명"),
                                   verbose_name=_("재선구분명"))
    gtelt_eraco = models.CharField(max_length=100,
                                   help_text=_("당선대수"),
                                   verbose_name=_("당선대수"))
    era_int = models.IntegerField(null=True,
                                  blank=True,
                                  help_text=_("대수 (숫자)"),
                                  verbose_name=_("대수"))
    nth_term = models.IntegerField(null=True,
                                   blank=True,
                                   help_text=_("선수 (숫자)"),
                                   verbose_name=_("선수"))
    ntr_div = models.CharField(max_length=10,
                               help_text=_("성별"),
                               verbose_name=_("성별"))
    naas_pic = models.URLField(blank=True,
                               help_text=_("국회의원사진 URL"),
                               verbose_name=_("국회의원 사진 URL"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['naas_nm']
        verbose_name = _("국회의원")
        verbose_name_plural = _("국회의원")

    def __str__(self):
        current_party_name = self.current_party.name if self.current_party else "정당정보없음"
        return f"{self.naas_nm} ({current_party_name})"

    def get_party_list(self):
        """Returns a list of parties from the plpt_nm field"""
        if not self.plpt_nm:
            return []
        return [
            party.strip() for party in self.plpt_nm.split('/')
            if party.strip()
        ]

    def get_current_party_name(self):
        """Returns the most recent (last) party from the party history with proper mapping"""
        parties = self.get_party_list()
        if not parties:
            return "정당정보없음"

        # Get the last (most recent) party
        current_party = parties[-1]

        # Apply party name mappings for consolidation
        party_mappings = {
            '민주통합당': '더불어민주당',
            '더불어민주연합': '더불어민주당',
            # Add other mappings as needed
        }

        return party_mappings.get(current_party, current_party)


class SpeakerPartyHistory(models.Model):
    speaker = models.ForeignKey(Speaker,
                                on_delete=models.CASCADE,
                                verbose_name=_("국회의원"))
    party = models.ForeignKey(Party,
                              on_delete=models.CASCADE,
                              verbose_name=_("정당"))
    order = models.PositiveIntegerField(help_text=_("정당 이력 순서 (0부터 시작)"),
                                        verbose_name=_("순서"))
    is_current = models.BooleanField(default=False,
                                     help_text=_("현재 소속 정당 여부"),
                                     verbose_name=_("현재 정당"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))

    class Meta:
        ordering = ['speaker', 'order']
        unique_together = ['speaker', 'party', 'order']
        verbose_name = _("국회의원 정당 이력")
        verbose_name_plural = _("국회의원 정당 이력")

    def __str__(self):
        return f"{self.speaker.naas_nm} - {self.party.name} ({self.order})"


class Statement(models.Model):
    session = models.ForeignKey(Session,
                                on_delete=models.CASCADE,
                                related_name='statements',
                                verbose_name=_("관련 회의"))
    bill = models.ForeignKey(Bill,
                             on_delete=models.CASCADE,
                             related_name='statements',
                             null=True,
                             blank=True,
                             verbose_name=_("관련 의안"))
    speaker = models.ForeignKey(Speaker,
                                on_delete=models.CASCADE,
                                related_name='statements',
                                verbose_name=_("발언자"))
    text = models.TextField(help_text=_("발언 내용"), verbose_name=_("발언 내용"))
    sentiment_score = models.FloatField(null=True,
                                        blank=True,
                                        help_text="감성 점수 (-1 ~ 1)",
                                        verbose_name=_("감성 점수"))
    sentiment_reason = models.TextField(blank=True,
                                        help_text=_("감성 분석 근거"),
                                        verbose_name=_("감성 분석 근거"))
    bill_relevance_score = models.FloatField(null=True,
                                             blank=True,
                                             help_text="의안 관련성 점수 (0-1)",
                                             verbose_name=_("의안 관련성 점수"))
    text_hash = models.CharField(max_length=64,
                                 blank=True,
                                 help_text=_("텍스트 해시"),
                                 verbose_name=_("텍스트 해시"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("발언")
        verbose_name_plural = _("발언")

    def __str__(self):
        return f"{self.speaker.naas_nm}의 발언 ({self.created_at})"

    @staticmethod
    def calculate_hash(text, speaker_code, session_id):
        """Calculate a hash for a statement based on text, speaker, and session"""
        import hashlib
        # Create a string combining the key identifying fields
        identifier = f"{text}|{speaker_code}|{session_id}"
        # Return SHA256 hash
        return hashlib.sha256(identifier.encode('utf-8')).hexdigest()

    def get_hash(self):
        """Get hash for this statement instance"""
        return self.calculate_hash(self.text, self.speaker.naas_cd,
                                   self.session.conf_id)


class Category(models.Model):
    """
    Major policy categories (대범주) from CSV data:
    - 경제정책 (Economic Policy)
    - 사회정책 (Social Policy) 
    - 외교안보정책 (Foreign Affairs & Security Policy)
    - 법행정제도 (Legal & Administrative System)
    - 과학기술정책 (Science & Technology Policy)
    - 문화체육정책 (Culture & Sports Policy)
    - 인권소수자정책 (Human Rights & Minority Policy)
    - 지역균형정책 (Regional Balance Policy)
    - 정치정책 (Political Policy)
    """
    name = models.CharField(max_length=100,
                            unique=True,
                            help_text=_("대범주명 (예: 경제정책, 사회정책)"),
                            verbose_name=_("대범주명"))
    description = models.TextField(blank=True,
                                   help_text=_("카테고리 설명"),
                                   verbose_name=_("카테고리 설명"))
    policy_area_code = models.CharField(max_length=20,
                                       blank=True,
                                       help_text=_("정책영역 코드"),
                                       verbose_name=_("정책영역 코드"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return self.name

    def get_subcategory_count(self):
        """Returns the number of subcategories under this category"""
        return self.subcategories.count()

    class Meta:
        ordering = ['name']
        verbose_name = "정책 대범주"
        verbose_name_plural = "정책 대범주 목록"


class Subcategory(models.Model):
    """
    Specific policy subcategories (소범주) from CSV data:
    Each subcategory belongs to a major category and represents
    specific policy positions or implementation approaches.
    """
    category = models.ForeignKey(Category,
                                 on_delete=models.CASCADE,
                                 related_name='subcategories',
                                 verbose_name=_("상위 대범주"))
    name = models.CharField(max_length=100,
                            help_text=_("소범주명 (예: 확장재정, 긴축재정)"),
                            verbose_name=_("소범주명"))
    description = models.TextField(blank=True,
                                   help_text=_("소범주 정책 설명"),
                                   verbose_name=_("소범주 설명"))
    policy_stance = models.CharField(max_length=50,
                                    blank=True,
                                    help_text=_("정책 성향 (진보/보수/중도)"),
                                    verbose_name=_("정책 성향"))
    implementation_approach = models.TextField(blank=True,
                                              help_text=_("구체적 실행 방안"),
                                              verbose_name=_("실행 방안"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return f"{self.category.name} > {self.name}"

    def get_related_bills_count(self):
        """Returns the number of bills related to this subcategory"""
        return self.bill_subcategories.count()

    class Meta:
        ordering = ['category__name', 'name']
        unique_together = ['category', 'name']
        verbose_name = "정책 소범주"
        verbose_name_plural = "정책 소범주 목록"


class BillCategoryMapping(models.Model):
    """Mapping between Bills and Categories with confidence scores"""
    bill = models.ForeignKey(Bill,
                            on_delete=models.CASCADE,
                            related_name='category_mappings',
                            verbose_name=_("의안"))
    category = models.ForeignKey(Category,
                                on_delete=models.CASCADE,
                                related_name='bill_mappings',
                                verbose_name=_("정책 대범주"))
    confidence_score = models.FloatField(default=0.0,
                                        help_text=_("LLM 분류 신뢰도 (0-1)"),
                                        verbose_name=_("분류 신뢰도"))
    is_primary = models.BooleanField(default=False,
                                    help_text=_("주요 범주 여부"),
                                    verbose_name=_("주요 범주"))
    analysis_method = models.CharField(max_length=50,
                                      default="llm_analysis",
                                      help_text=_("분석 방법 (llm_analysis, manual, etc.)"),
                                      verbose_name=_("분석 방법"))
    created_at = models.DateTimeField(auto_now_add=True,
                                     verbose_name=_("생성일시"))

    def __str__(self):
        return f"{self.bill.bill_nm[:30]}... - {self.category.name}"

    class Meta:
        ordering = ['-confidence_score', '-is_primary']
        unique_together = ['bill', 'category']
        verbose_name = "의안-대범주 매핑"
        verbose_name_plural = "의안-대범주 매핑 목록"


class BillSubcategoryMapping(models.Model):
    """Mapping between Bills and Subcategories with detailed analysis"""
    bill = models.ForeignKey(Bill,
                            on_delete=models.CASCADE,
                            related_name='subcategory_mappings',
                            verbose_name=_("의안"))
    subcategory = models.ForeignKey(Subcategory,
                                   on_delete=models.CASCADE,
                                   related_name='bill_subcategories',
                                   verbose_name=_("정책 소범주"))
    relevance_score = models.FloatField(default=0.0,
                                       help_text=_("관련성 점수 (0-1)"),
                                       verbose_name=_("관련성 점수"))
    supporting_evidence = models.TextField(blank=True,
                                          help_text=_("분류 근거 텍스트"),
                                          verbose_name=_("분류 근거"))
    extracted_keywords = models.JSONField(default=list,
                                         blank=True,
                                         help_text=_("추출된 관련 키워드"),
                                         verbose_name=_("관련 키워드"))
    policy_position = models.CharField(max_length=20,
                                      blank=True,
                                      choices=[
                                          ('support', '지지'),
                                          ('oppose', '반대'),
                                          ('neutral', '중립'),
                                          ('unknown', '불명')
                                      ],
                                      help_text=_("해당 정책에 대한 입장"),
                                      verbose_name=_("정책 입장"))
    created_at = models.DateTimeField(auto_now_add=True,
                                     verbose_name=_("생성일시"))

    def __str__(self):
        return f"{self.bill.bill_nm[:30]}... - {self.subcategory.name}"

    class Meta:
        ordering = ['-relevance_score']
        unique_together = ['bill', 'subcategory']
        verbose_name = "의안-소범주 매핑"
        verbose_name_plural = "의안-소범주 매핑 목록"


class StatementCategory(models.Model):
    statement = models.ForeignKey(Statement,
                                  on_delete=models.CASCADE,
                                  related_name='categories',
                                  verbose_name=_("발언"))
    category = models.ForeignKey(Category,
                                 on_delete=models.CASCADE,
                                 verbose_name=_("카테고리"))
    subcategory = models.ForeignKey(Subcategory,
                                    on_delete=models.CASCADE,
                                    null=True,
                                    blank=True,
                                    verbose_name=_("하위카테고리"))
    confidence_score = models.FloatField(default=0.0,
                                         help_text=_("분류 신뢰도 (0-1)"),
                                         verbose_name=_("분류 신뢰도"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))

    def __str__(self):
        return f"{self.statement} - {self.category.name}"

    class Meta:
        ordering = ['-confidence_score']
        unique_together = ['statement', 'category']
        verbose_name = "발언 카테고리"
        verbose_name_plural = "발언 카테고리 목록"


class VotingRecord(models.Model):
    VOTE_CHOICES = [
        ('찬성', '찬성'),
        ('반대', '반대'),
        ('기권', '기권'),
        ('불참', '불참'),
        ('무효', '무효'),
    ]

    bill = models.ForeignKey(Bill,
                             on_delete=models.CASCADE,
                             related_name='voting_records',
                             verbose_name=_("관련 의안"))
    speaker = models.ForeignKey(Speaker,
                                on_delete=models.CASCADE,
                                related_name='voting_records',
                                verbose_name=_("투표자"))
    vote_result = models.CharField(max_length=10,
                                   choices=VOTE_CHOICES,
                                   verbose_name=_("투표 결과"))
    vote_date = models.DateTimeField(null=True,
                                     blank=True,
                                     verbose_name=_("투표 일시"))
    sentiment_score = models.FloatField(default=0.0,
                                        help_text=_("투표 감성 점수 (-1 ~ 1)"),
                                        verbose_name=_("투표 감성 점수"))
    session = models.ForeignKey(Session,
                                on_delete=models.CASCADE,
                                related_name='voting_records',
                                null=True,
                                blank=True,
                                verbose_name=_("관련 회의"))
    created_at = models.DateTimeField(auto_now_add=True,
                                      verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def save(self, *args, **kwargs):
        # Auto-calculate sentiment score based on vote result
        if self.vote_result == '찬성':
            self.sentiment_score = 1.0
        elif self.vote_result == '반대':
            self.sentiment_score = -1.0
        else:  # 기권, 불참, 무효
            self.sentiment_score = 0.0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.speaker.naas_nm} - {self.bill.bill_nm[:20]}... ({self.vote_result})"

    class Meta:
        ordering = ['-vote_date']
        unique_together = ['bill', 'speaker']
        verbose_name = "투표 기록"
        verbose_name_plural = "투표 기록"


@receiver(pre_save, sender=Statement)
def calculate_statement_hash(sender, instance, **kwargs):
    """Automatically calculate hash before saving statement"""
    if instance.text and instance.speaker and instance.session:
        instance.text_hash = Statement.calculate_hash(instance.text,
                                                      instance.speaker.naas_cd,
                                                      instance.session.conf_id)
