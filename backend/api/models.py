from django.db import models
from django.utils.translation import gettext_lazy as _

class Session(models.Model):
    conf_id = models.CharField(max_length=50, primary_key=True)
    era_co = models.CharField(max_length=20, help_text=_("대수"))
    sess = models.CharField(max_length=20, help_text=_("회기"))
    dgr = models.CharField(max_length=20, help_text=_("차수"))
    conf_dt = models.DateField(help_text=_("회의일자"))
    conf_knd = models.CharField(max_length=100, help_text=_("회의종류"))
    cmit_nm = models.CharField(max_length=100, help_text=_("위원회명"))
    conf_plc = models.CharField(max_length=200, blank=True, help_text=_("회의장소"))
    bg_ptm = models.TimeField(help_text=_("시작시간"))
    ed_ptm = models.TimeField(help_text=_("종료시간"))
    down_url = models.URLField(help_text=_("PDF 다운로드 URL"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-conf_dt', '-bg_ptm']
        verbose_name = _("회의")
        verbose_name_plural = _("회의")

    def __str__(self):
        return f"{self.era_co} {self.sess} {self.dgr} ({self.conf_dt})"

class Bill(models.Model):
    bill_id = models.CharField(max_length=100, primary_key=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='bills')
    bill_nm = models.CharField(max_length=500, help_text=_("의안명"))
    link_url = models.URLField(help_text=_("의안 상세 URL"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("의안")
        verbose_name_plural = _("의안")

    def __str__(self):
        return self.bill_nm

class Speaker(models.Model):
    naas_cd = models.CharField(max_length=20, primary_key=True)
    naas_nm = models.CharField(max_length=100, help_text=_("국회의원명"))
    naas_ch_nm = models.CharField(max_length=100, blank=True, help_text=_("국회의원한자명"))
    plpt_nm = models.CharField(max_length=100, help_text=_("정당명"))
    elecd_nm = models.CharField(max_length=200, help_text=_("선거구명"))
    elecd_div_nm = models.CharField(max_length=100, help_text=_("선거구구분명"))
    cmit_nm = models.CharField(max_length=100, blank=True, help_text=_("위원회명"))
    blng_cmit_nm = models.CharField(max_length=200, blank=True, help_text=_("소속위원회명"))
    rlct_div_nm = models.CharField(max_length=50, help_text=_("재선구분명"))
    gtelt_eraco = models.CharField(max_length=100, help_text=_("당선대수"))
    ntr_div = models.CharField(max_length=10, help_text=_("성별"))
    naas_pic = models.URLField(blank=True, help_text=_("국회의원사진 URL"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['naas_nm']
        verbose_name = _("국회의원")
        verbose_name_plural = _("국회의원")

    def __str__(self):
        return f"{self.naas_nm} ({self.plpt_nm})"

class Statement(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='statements')
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='statements', null=True, blank=True)
    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name='statements')
    text = models.TextField(help_text=_("발언 내용"))
    sentiment_score = models.FloatField(help_text=_("감성 점수 (-1 ~ 1)"))
    sentiment_reason = models.TextField(help_text=_("감성 분석 근거"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("발언")
        verbose_name_plural = _("발언")

    def __str__(self):
        return f"{self.speaker.naas_nm}의 발언 ({self.created_at})"
