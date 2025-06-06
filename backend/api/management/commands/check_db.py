
from django.core.management.base import BaseCommand
from api.models import Session, Bill, Speaker, Statement


class Command(BaseCommand):
    help = 'Check current database state'

    def handle(self, *args, **options):
        self.stdout.write('📊 Current Database Status:')
        self.stdout.write(f'   Sessions: {Session.objects.count()}')
        self.stdout.write(f'   Bills: {Bill.objects.count()}')
        self.stdout.write(f'   Speakers: {Speaker.objects.count()}')
        self.stdout.write(f'   Statements: {Statement.objects.count()}')
        
        if Session.objects.exists():
            # Latest session by conference date
            latest_by_date = Session.objects.order_by('-conf_dt', '-created_at').first()
            self.stdout.write(f'📝 Latest Session by Date: {latest_by_date.conf_id} - {latest_by_date.era_co} {latest_by_date.sess} {latest_by_date.dgr} ({latest_by_date.conf_dt})')
            
            # Most recently added session
            latest_added = Session.objects.order_by('-created_at').first()
            self.stdout.write(f'🆕 Most Recently Added: {latest_added.conf_id} - added {latest_added.created_at.strftime("%Y-%m-%d %H:%M")}')
            
            # Sessions with statements
            sessions_with_statements = Session.objects.filter(statements__isnull=False).distinct().count()
            self.stdout.write(f'📄 Sessions with Statements: {sessions_with_statements}')
            
            # Latest session with statements
            latest_with_statements = Session.objects.filter(statements__isnull=False).order_by('-conf_dt').first()
            if latest_with_statements:
                statement_count = latest_with_statements.statements.count()
                self.stdout.write(f'💬 Latest with Statements: {latest_with_statements.conf_id} ({statement_count} statements)')
        else:
            self.stdout.write('❌ No sessions found in database')
