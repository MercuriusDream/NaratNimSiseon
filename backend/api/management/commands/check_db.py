
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
            latest_session = Session.objects.first()
            self.stdout.write(f'📝 Latest Session: {latest_session.conf_id} - {latest_session.sess}')
        else:
            self.stdout.write('❌ No sessions found in database')
