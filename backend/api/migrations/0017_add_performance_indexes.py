
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_bill_proposer_fields'),
    ]

    operations = [
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_session_era_co ON api_session(era_co);",
            reverse_sql="DROP INDEX IF EXISTS idx_session_era_co;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_session_conf_dt ON api_session(conf_dt DESC);",
            reverse_sql="DROP INDEX IF EXISTS idx_session_conf_dt;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_statement_session_era ON api_statement(session_id) WHERE session_id IN (SELECT conf_id FROM api_session WHERE era_co IN ('제22대', '22'));",
            reverse_sql="DROP INDEX IF EXISTS idx_statement_session_era;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_statement_created_at ON api_statement(created_at DESC);",
            reverse_sql="DROP INDEX IF EXISTS idx_statement_created_at;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_speaker_era ON api_speaker(gtelt_eraco);",
            reverse_sql="DROP INDEX IF EXISTS idx_speaker_era;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_speaker_party ON api_speaker(plpt_nm);",
            reverse_sql="DROP INDEX IF EXISTS idx_speaker_party;"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_bill_created_at ON api_bill(created_at DESC);",
            reverse_sql="DROP INDEX IF EXISTS idx_bill_created_at;"
        ),
    ]
