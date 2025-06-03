
from django.core.management.base import BaseCommand
from api.models import Session, Bill, Speaker, Statement
from django.db.models import Count, Avg
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Check the status of data collection and processing'

    def handle(self, *args, **options):
        self.stdout.write('📊 Data Collection Status Report')
        self.stdout.write('=' * 50)
        
        # Basic counts
        session_count = Session.objects.count()
        bill_count = Bill.objects.count()
        speaker_count = Speaker.objects.count()
        statement_count = Statement.objects.count()
        
        self.stdout.write(f'📋 Sessions: {session_count}')
        self.stdout.write(f'📄 Bills: {bill_count}')
        self.stdout.write(f'👥 Speakers: {speaker_count}')
        self.stdout.write(f'💬 Statements: {statement_count}')
        
        # Recent activity
        self.stdout.write('\n⏰ Recent Activity (Last 24 hours):')
        yesterday = datetime.now() - timedelta(hours=24)
        
        recent_sessions = Session.objects.filter(created_at__gte=yesterday).count()
        recent_bills = Bill.objects.filter(created_at__gte=yesterday).count()
        recent_statements = Statement.objects.filter(created_at__gte=yesterday).count()
        
        self.stdout.write(f'📋 New Sessions: {recent_sessions}')
        self.stdout.write(f'📄 New Bills: {recent_bills}')
        self.stdout.write(f'💬 New Statements: {recent_statements}')
        
        # Processing status
        self.stdout.write('\n🔄 Processing Status:')
        sessions_with_statements = Session.objects.annotate(
            statement_count=Count('statements')
        ).filter(statement_count__gt=0).count()
        
        sessions_with_pdfs = Session.objects.exclude(down_url='').count()
        
        self.stdout.write(f'📋 Sessions with PDF URLs: {sessions_with_pdfs}')
        self.stdout.write(f'📋 Sessions with processed statements: {sessions_with_statements}')
        
        if session_count > 0:
            processing_rate = (sessions_with_statements / session_count) * 100
            self.stdout.write(f'📊 Processing completion rate: {processing_rate:.1f}%')
        
        # Sentiment analysis stats
        if statement_count > 0:
            avg_sentiment = Statement.objects.aggregate(
                avg_sentiment=Avg('sentiment_score')
            )['avg_sentiment']
            
            positive_statements = Statement.objects.filter(sentiment_score__gt=0.3).count()
            negative_statements = Statement.objects.filter(sentiment_score__lt=-0.3).count()
            neutral_statements = statement_count - positive_statements - negative_statements
            
            self.stdout.write('\n😊 Sentiment Analysis:')
            self.stdout.write(f'📊 Average sentiment: {avg_sentiment:.3f}')
            self.stdout.write(f'😊 Positive statements: {positive_statements}')
            self.stdout.write(f'😐 Neutral statements: {neutral_statements}')
            self.stdout.write(f'😔 Negative statements: {negative_statements}')
        
        # Latest processed data
        latest_session = Session.objects.order_by('-created_at').first()
        latest_statement = Statement.objects.order_by('-created_at').first()
        
        if latest_session:
            self.stdout.write(f'\n🕐 Latest session: {latest_session.conf_id} ({latest_session.created_at})')
        
        if latest_statement:
            self.stdout.write(f'🕐 Latest statement: {latest_statement.created_at}')
            self.stdout.write(f'👤 Speaker: {latest_statement.speaker.naas_nm}')
            self.stdout.write(f'😊 Sentiment: {latest_statement.sentiment_score:.2f}')
