from django.contrib import admin
from .models import Session, Bill, Speaker, Statement

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('conf_id', 'era_co', 'sess', 'dgr', 'conf_dt', 'conf_knd')
    list_filter = ('era_co', 'conf_knd')
    search_fields = ('conf_id', 'sess', 'dgr')
    date_hierarchy = 'conf_dt'

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ('bill_id', 'session', 'bill_nm')
    list_filter = ('session__era_co', 'session__sess')
    search_fields = ('bill_id', 'bill_nm')
    raw_id_fields = ('session',)

@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ('naas_nm', 'plpt_nm', 'elecd_nm', 'gtelt_eraco')
    list_filter = ('plpt_nm', 'gtelt_eraco')
    search_fields = ('naas_nm', 'naas_ch_nm', 'elecd_nm')

@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ('speaker', 'session', 'sentiment_score', 'created_at')
    list_filter = ('session__era_co', 'speaker__plpt_nm')
    search_fields = ('text', 'speaker__naas_nm')
    raw_id_fields = ('session', 'bill', 'speaker')
