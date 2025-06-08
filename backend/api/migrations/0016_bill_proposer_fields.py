
# Generated migration for Bill proposer fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_statement_bill_relevance_score_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='bill',
            name='bill_no',
            field=models.CharField(blank=True, help_text='의안번호', max_length=100, verbose_name='의안번호'),
        ),
        migrations.AddField(
            model_name='bill',
            name='proposer',
            field=models.CharField(default='국회', help_text='제안자/제안위원회', max_length=200, verbose_name='제안자'),
        ),
        migrations.AddField(
            model_name='bill',
            name='propose_dt',
            field=models.CharField(blank=True, help_text='제안일자', max_length=50, verbose_name='제안일자'),
        ),
        migrations.AlterField(
            model_name='bill',
            name='link_url',
            field=models.URLField(blank=True, help_text='의안 상세 URL', verbose_name='의안 상세 URL'),
        ),
    ]
