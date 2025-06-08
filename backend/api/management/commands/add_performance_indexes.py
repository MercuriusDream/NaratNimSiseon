
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Add database indexes for better API performance'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            indexes = [
                # Statement indexes
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_session_era ON api_statement(session_id) WHERE session_id IN (SELECT conf_id FROM api_session WHERE era_co IN (\'22\', \'제22대\'));',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_sentiment ON api_statement(sentiment_score) WHERE sentiment_score IS NOT NULL;',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_speaker_party ON api_statement(speaker_id);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_created_at ON api_statement(created_at DESC);',

                # Session indexes  
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_era_date ON api_session(era_co, conf_dt DESC);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_conf_dt ON api_session(conf_dt DESC);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_era_only ON api_session(era_co);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_sess_dgr ON api_session(sess, dgr);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_22nd ON api_session(conf_dt DESC) WHERE era_co IN (\'22\', \'제22대\');',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_era_22_date ON api_session(conf_dt DESC) WHERE era_co IN (\'22\', \'제22대\');',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_era_sess_dgr ON api_session(era_co, sess, dgr);',

                # Speaker indexes
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_speaker_assembly_era ON api_speaker(gtelt_eraco) WHERE gtelt_eraco LIKE \'%22%\';',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_speaker_party ON api_speaker(plpt_nm);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_speaker_current_party ON api_speaker(current_party_id);',

                # Bill indexes
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_session_era ON api_bill(session_id);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_created_at ON api_bill(created_at DESC);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bill_session_22nd ON api_bill(session_id) WHERE session_id IN (SELECT conf_id FROM api_session WHERE era_co IN (\'22\', \'제22대\'));',

                # Party indexes
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_party_assembly_era ON api_party(assembly_era);',

                # Composite indexes for complex queries
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_session_sentiment ON api_statement(session_id, sentiment_score);',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_speaker_session ON api_statement(speaker_id, session_id);',
            ]

            for index_sql in indexes:
                try:
                    self.stdout.write(f'Creating index: {index_sql[:60]}...')
                    cursor.execute(index_sql)
                    self.stdout.write(self.style.SUCCESS('✅ Index created successfully'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠️  Index already exists or error: {e}'))

        self.stdout.write(self.style.SUCCESS('🚀 Database indexing completed!'))
