
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Create and run migration for VotingRecord model'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Creating migration for VotingRecord model...')
        )
        
        # Create the migration SQL
        migration_sql = """
        CREATE TABLE IF NOT EXISTS api_votingrecord (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id VARCHAR(100) NOT NULL,
            speaker_id VARCHAR(20) NOT NULL,
            vote_result VARCHAR(10) NOT NULL,
            vote_date DATETIME NOT NULL,
            sentiment_score REAL NOT NULL,
            session_id VARCHAR(50),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY (bill_id) REFERENCES api_bill (bill_id),
            FOREIGN KEY (speaker_id) REFERENCES api_speaker (naas_cd),
            FOREIGN KEY (session_id) REFERENCES api_session (conf_id),
            UNIQUE (bill_id, speaker_id)
        );
        """
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(migration_sql)
            
            self.stdout.write(
                self.style.SUCCESS('✅ VotingRecord table created successfully!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error creating VotingRecord table: {e}')
            )
