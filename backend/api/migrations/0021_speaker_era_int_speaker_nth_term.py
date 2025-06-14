# Generated by Django 5.0.2 on 2025-06-09 22:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_alter_category_options_alter_subcategory_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='speaker',
            name='era_int',
            field=models.IntegerField(blank=True, help_text='대수 (숫자)', null=True, verbose_name='대수'),
        ),
        migrations.AddField(
            model_name='speaker',
            name='nth_term',
            field=models.IntegerField(blank=True, help_text='선수 (숫자)', null=True, verbose_name='선수'),
        ),
    ]
