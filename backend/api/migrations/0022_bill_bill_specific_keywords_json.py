# Generated by Django 5.0.2 on 2025-06-10 15:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_speaker_era_int_speaker_nth_term'),
    ]

    operations = [
        migrations.AddField(
            model_name='bill',
            name='bill_specific_keywords_json',
            field=models.JSONField(blank=True, default=list, help_text='의안별 특화 키워드 (JSON 형태)', verbose_name='의안별 특화 키워드 JSON'),
        ),
    ]
