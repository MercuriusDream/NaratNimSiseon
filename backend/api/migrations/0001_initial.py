# Generated by Django 5.0.2 on 2025-06-02 18:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Session',
            fields=[
                ('conf_id', models.CharField(max_length=50, primary_key=True, serialize=False)),
                ('era_co', models.CharField(help_text='대수', max_length=20)),
                ('sess', models.CharField(help_text='회기', max_length=20)),
                ('dgr', models.CharField(help_text='차수', max_length=20)),
                ('conf_dt', models.DateField(help_text='회의일자')),
                ('conf_knd', models.CharField(help_text='회의종류', max_length=100)),
                ('cmit_nm', models.CharField(help_text='위원회명', max_length=100)),
                ('conf_plc', models.CharField(blank=True, help_text='회의장소', max_length=200)),
                ('bg_ptm', models.TimeField(help_text='시작시간')),
                ('ed_ptm', models.TimeField(help_text='종료시간')),
                ('down_url', models.URLField(help_text='PDF 다운로드 URL')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': '회의',
                'verbose_name_plural': '회의',
                'ordering': ['-conf_dt', '-bg_ptm'],
            },
        ),
        migrations.CreateModel(
            name='Speaker',
            fields=[
                ('naas_cd', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('naas_nm', models.CharField(help_text='국회의원명', max_length=100)),
                ('naas_ch_nm', models.CharField(blank=True, help_text='국회의원한자명', max_length=100)),
                ('plpt_nm', models.CharField(help_text='정당명', max_length=100)),
                ('elecd_nm', models.CharField(help_text='선거구명', max_length=200)),
                ('elecd_div_nm', models.CharField(help_text='선거구구분명', max_length=100)),
                ('cmit_nm', models.CharField(blank=True, help_text='위원회명', max_length=100)),
                ('blng_cmit_nm', models.CharField(blank=True, help_text='소속위원회명', max_length=200)),
                ('rlct_div_nm', models.CharField(help_text='재선구분명', max_length=50)),
                ('gtelt_eraco', models.CharField(help_text='당선대수', max_length=100)),
                ('ntr_div', models.CharField(help_text='성별', max_length=10)),
                ('naas_pic', models.URLField(blank=True, help_text='국회의원사진 URL')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': '국회의원',
                'verbose_name_plural': '국회의원',
                'ordering': ['naas_nm'],
            },
        ),
        migrations.CreateModel(
            name='Bill',
            fields=[
                ('bill_id', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('bill_nm', models.CharField(help_text='의안명', max_length=500)),
                ('link_url', models.URLField(help_text='의안 상세 URL')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bills', to='api.session')),
            ],
            options={
                'verbose_name': '의안',
                'verbose_name_plural': '의안',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Statement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(help_text='발언 내용')),
                ('sentiment_score', models.FloatField(help_text='감성 점수 (-1 ~ 1)')),
                ('sentiment_reason', models.TextField(help_text='감성 분석 근거')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bill', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='statements', to='api.bill')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='statements', to='api.session')),
                ('speaker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='statements', to='api.speaker')),
            ],
            options={
                'verbose_name': '발언',
                'verbose_name_plural': '발언',
                'ordering': ['-created_at'],
            },
        ),
    ]
