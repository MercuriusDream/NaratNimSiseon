
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Add database indexes specifically for sentiment analysis queries'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            sentiment_indexes = [
                # Sentiment score indexes for filtering and sorting
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_sentiment_score ON api_statement(sentiment_score) WHERE sentiment_score IS NOT NULL;',
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_sentiment_range ON api_statement(sentiment_score) WHERE sentiment_score BETWEEN -1.0 AND 1.0;',
                
                # Composite indexes for sentiment analysis by party
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_speaker_sentiment ON api_statement(speaker_id, sentiment_score) WHERE sentiment_score IS NOT NULL;',
                
                # Indexes for sentiment analysis by session
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_session_sentiment_score ON api_statement(session_id, sentiment_score) WHERE sentiment_score IS NOT NULL;',
                
                # Index for 22nd Assembly sentiment analysis
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_22nd_sentiment ON api_statement(sentiment_score, created_at) WHERE sentiment_score IS NOT NULL;',
                
                # Index for non-null sentiment scores with text length (for filtering meaningful statements)
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_statement_sentiment_with_text ON api_statement(sentiment_score, length(text)) WHERE sentiment_score IS NOT NULL AND length(text) > 50;',
                
                # Speaker party sentiment analysis
                'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_speaker_current_party_sentiment ON api_speaker(current_party_id) WHERE current_party_id IS NOT NULL;',
            ]

            for index_sql in sentiment_indexes:
                try:
                    self.stdout.write(f'Creating sentiment index: {index_sql[:80]}...')
                    cursor.execute(index_sql)
                    self.stdout.write(self.style.SUCCESS('✅ Sentiment index created successfully'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠️  Sentiment index already exists or error: {e}'))

        self.stdout.write(self.style.SUCCESS('🚀 Sentiment analysis indexing completed!'))
