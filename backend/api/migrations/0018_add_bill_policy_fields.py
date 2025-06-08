
# Generated migration to add policy fields to Bill model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_add_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='bill',
            name='policy_categories',
            field=models.JSONField(blank=True, default=list, help_text='정책 카테고리 목록', verbose_name='정책 카테고리'),
        ),
        migrations.AddField(
            model_name='bill',
            name='key_policy_phrases',
            field=models.JSONField(blank=True, default=list, help_text='핵심 정책 어구 목록', verbose_name='핵심 정책 어구'),
        ),
        migrations.AddField(
            model_name='bill',
            name='bill_specific_keywords_found',
            field=models.JSONField(blank=True, default=list, help_text='의안 관련 키워드 목록', verbose_name='의안 관련 키워드'),
        ),
    ]
