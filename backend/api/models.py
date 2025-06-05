from django.db import models
from django.utils.translation import gettext_lazy as _

class Session(models.Model):
    conf_id = models.CharField(max_length=50, primary_key=True, verbose_name=_("회의 ID"))
    era_co = models.CharField(max_length=20, help_text=_("대수"), verbose_name=_("대수"))
    sess = models.CharField(max_length=20, help_text=_("회기"), verbose_name=_("회기"))
    dgr = models.CharField(max_length=20, help_text=_("차수"), verbose_name=_("차수"))
    conf_dt = models.DateField(help_text=_("회의일자"), verbose_name=_("회의일자"))
    conf_knd = models.CharField(max_length=100, help_text=_("회의종류"), verbose_name=_("회의종류"))
    cmit_nm = models.CharField(max_length=100, help_text=_("위원회명"), verbose_name=_("위원회명"))
    conf_plc = models.CharField(max_length=200, blank=True, help_text=_("회의장소"), verbose_name=_("회의장소"))
    bg_ptm = models.TimeField(help_text=_("시작시간"), verbose_name=_("시작시간"))
    ed_ptm = models.TimeField(null=True, blank=True, help_text=_("종료시간"), verbose_name=_("종료시간"))
    down_url = models.URLField(help_text=_("PDF 다운로드 URL"), verbose_name=_("PDF 다운로드 URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-conf_dt', '-bg_ptm']
        verbose_name = _("회의")
        verbose_name_plural = _("회의")

    def __str__(self):
        return f"{self.era_co} {self.sess} {self.dgr} ({self.conf_dt})"

class Bill(models.Model):
    bill_id = models.CharField(max_length=100, primary_key=True, verbose_name=_("의안 ID"))
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='bills', verbose_name=_("관련 회의"))
    bill_nm = models.CharField(max_length=500, help_text=_("의안명"), verbose_name=_("의안명"))
    link_url = models.URLField(help_text=_("의안 상세 URL"), verbose_name=_("의안 상세 URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("의안")
        verbose_name_plural = _("의안")

    def __str__(self):
        return self.bill_nm

class Speaker(models.Model):
    naas_cd = models.CharField(max_length=20, primary_key=True, verbose_name=_("국회의원 코드"))
    naas_nm = models.CharField(max_length=100, help_text=_("국회의원명"), verbose_name=_("국회의원명"))
    naas_ch_nm = models.CharField(max_length=100, blank=True, help_text=_("국회의원한자명"), verbose_name=_("국회의원 한자명"))
    plpt_nm = models.CharField(max_length=100, help_text=_("정당명"), verbose_name=_("정당명"))
    elecd_nm = models.CharField(max_length=200, help_text=_("선거구명"), verbose_name=_("선거구명"))
    elecd_div_nm = models.CharField(max_length=100, help_text=_("선거구구분명"), verbose_name=_("선거구 구분명"))
    cmit_nm = models.CharField(max_length=100, blank=True, help_text=_("대표위원회명"), verbose_name=_("대표위원회명"))
    blng_cmit_nm = models.CharField(max_length=200, blank=True, help_text=_("소속위원회명"), verbose_name=_("소속위원회명"))
    rlct_div_nm = models.CharField(max_length=50, help_text=_("재선구분명"), verbose_name=_("재선구분명"))
    gtelt_eraco = models.CharField(max_length=100, help_text=_("당선대수"), verbose_name=_("당선대수"))
    ntr_div = models.CharField(max_length=10, help_text=_("성별"), verbose_name=_("성별"))
    naas_pic = models.URLField(blank=True, help_text=_("국회의원사진 URL"), verbose_name=_("국회의원 사진 URL"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['naas_nm']
        verbose_name = _("국회의원")
        verbose_name_plural = _("국회의원")

    def __str__(self):
        return f"{self.naas_nm} ({self.plpt_nm})"

class Statement(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='statements', verbose_name=_("관련 회의"))
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='statements', null=True, blank=True, verbose_name=_("관련 의안"))
    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name='statements', verbose_name=_("발언자"))
    text = models.TextField(help_text=_("발언 내용"), verbose_name=_("발언 내용"))
    sentiment_score = models.FloatField(help_text=_("감성 점수 (-1 ~ 1)"), verbose_name=_("감성 점수"))
    sentiment_reason = models.TextField(help_text=_("감성 분석 근거"), verbose_name=_("감성 분석 근거"))
    category_analysis = models.TextField(blank=True, help_text=_("카테고리 분석 결과"), verbose_name=_("카테고리 분석 결과"))
    policy_keywords = models.TextField(blank=True, help_text=_("정책 키워드"), verbose_name=_("정책 키워드"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("발언")
        verbose_name_plural = _("발언")

    def __str__(self):
        return f"{self.speaker.naas_nm}의 발언 ({self.created_at})"


class Party(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text=_("정당명"), verbose_name=_("정당명"))
    logo_url = models.URLField(blank=True, null=True, help_text=_("정당 로고 이미지 URL"), verbose_name=_("정당 로고 URL"))
    slogan = models.CharField(max_length=255, blank=True, help_text=_("정당 슬로건"), verbose_name=_("정당 슬로건"))
    description = models.TextField(blank=True, help_text=_("정당 설명"), verbose_name=_("정당 설명"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "정당"
        verbose_name_plural = "정당 목록"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text=_("카테고리명"), verbose_name=_("카테고리명"))
    description = models.TextField(blank=True, help_text=_("카테고리 설명"), verbose_name=_("카테고리 설명"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "카테고리"
        verbose_name_plural = "카테고리 목록"


class Subcategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories', verbose_name=_("상위 카테고리"))
    name = models.CharField(max_length=100, help_text=_("하위카테고리명"), verbose_name=_("하위카테고리명"))
    description = models.TextField(blank=True, help_text=_("하위카테고리 설명"), verbose_name=_("하위카테고리 설명"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("수정일시"))

    def __str__(self):
        return f"{self.category.name} > {self.name}"

    class Meta:
        ordering = ['category__name', 'name']
        unique_together = ['category', 'name']
        verbose_name = "하위카테고리"
        verbose_name_plural = "하위카테고리 목록"


class StatementCategory(models.Model):
    statement = models.ForeignKey(Statement, on_delete=models.CASCADE, related_name='categories', verbose_name=_("발언"))
    category = models.ForeignKey(Category, on_delete=models.CASCADE, verbose_name=_("카테고리"))
    subcategory = models.ForeignKey(Subcategory, on_delete=models.CASCADE, null=True, blank=True, verbose_name=_("하위카테고리"))
    confidence_score = models.FloatField(default=0.0, help_text=_("분류 신뢰도 (0-1)"), verbose_name=_("분류 신뢰도"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("생성일시"))

    def __str__(self):
        return f"{self.statement} - {self.category.name}"

    class Meta:
        ordering = ['-confidence_score']
        unique_together = ['statement', 'category']
        verbose_name = "발언 카테고리"
        verbose_name_plural = "발언 카테고리 목록"
