
from django.core.management.base import BaseCommand
from api.models import Statement
from django.db.models import Count, Avg, Min, Max, Q
import numpy as np


class Command(BaseCommand):
    help = 'Check the current status of sentiment scores in the database'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('📊 Checking sentiment score status...')
        )
        
        # Total statements
        total_statements = Statement.objects.filter(
            session__era_co__in=['22', '제22대']
        ).count()
        
        # Statements with sentiment scores
        with_sentiment = Statement.objects.filter(
            sentiment_score__isnull=False,
            session__era_co__in=['22', '제22대']
        ).exclude(sentiment_score=0.0)
        
        with_sentiment_count = with_sentiment.count()
        
        # Statements without sentiment scores
        without_sentiment = Statement.objects.filter(
            Q(sentiment_score__isnull=True) | Q(sentiment_score=0.0),
            session__era_co__in=['22', '제22대']
        ).count()
        
        self.stdout.write('')
        self.stdout.write('📈 Sentiment Score Coverage:')
        self.stdout.write(f'   Total statements (22nd Assembly): {total_statements:,}')
        self.stdout.write(f'   With sentiment scores: {with_sentiment_count:,} ({(with_sentiment_count/total_statements*100):.1f}%)')
        self.stdout.write(f'   Without sentiment scores: {without_sentiment:,} ({(without_sentiment/total_statements*100):.1f}%)')
        
        if with_sentiment_count > 0:
            # Sentiment statistics
            sentiment_stats = with_sentiment.aggregate(
                avg_sentiment=Avg('sentiment_score'),
                min_sentiment=Min('sentiment_score'),
                max_sentiment=Max('sentiment_score')
            )
            
            self.stdout.write('')
            self.stdout.write('📊 Current Sentiment Distribution:')
            self.stdout.write(f'   Average sentiment: {sentiment_stats["avg_sentiment"]:.3f}')
            self.stdout.write(f'   Range: {sentiment_stats["min_sentiment"]:.3f} to {sentiment_stats["max_sentiment"]:.3f}')
            
            # Sentiment range distribution
            positive_count = with_sentiment.filter(sentiment_score__gt=0.1).count()
            neutral_count = with_sentiment.filter(sentiment_score__gte=-0.1, sentiment_score__lte=0.1).count()
            negative_count = with_sentiment.filter(sentiment_score__lt=-0.1).count()
            
            self.stdout.write('')
            self.stdout.write('🎯 Sentiment Categories:')
            self.stdout.write(f'   Positive (>0.1): {positive_count:,} ({(positive_count/with_sentiment_count*100):.1f}%)')
            self.stdout.write(f'   Neutral (-0.1 to 0.1): {neutral_count:,} ({(neutral_count/with_sentiment_count*100):.1f}%)')
            self.stdout.write(f'   Negative (<-0.1): {negative_count:,} ({(negative_count/with_sentiment_count*100):.1f}%)')
            
            # Sample of sentiment scores
            self.stdout.write('')
            self.stdout.write('📝 Sample Sentiment Scores:')
            sample_statements = with_sentiment.order_by('?')[:5]
            for stmt in sample_statements:
                self.stdout.write(
                    f'   {stmt.sentiment_score:.3f} - {stmt.speaker.naas_nm} '
                    f'({stmt.text[:50]}...)'
                )
            
            # Party distribution (if available)
            party_sentiment = with_sentiment.values(
                'speaker__current_party__name'
            ).annotate(
                count=Count('id'),
                avg_sentiment=Avg('sentiment_score')
            ).filter(
                speaker__current_party__name__isnull=False
            ).order_by('-count')[:5]
            
            if party_sentiment:
                self.stdout.write('')
                self.stdout.write('🏛️  Top Parties by Statement Count (with sentiment):')
                for party in party_sentiment:
                    party_name = party['speaker__current_party__name']
                    count = party['count']
                    avg_sent = party['avg_sentiment']
                    self.stdout.write(f'   {party_name}: {count:,} statements, avg sentiment: {avg_sent:.3f}')
        
        else:
            self.stdout.write('')
            self.stdout.write('⚠️  No statements with sentiment scores found!')
        
        self.stdout.write('')
        if without_sentiment > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'💡 Recommendation: Run "python manage.py populate_sentiment_scores" '
                    f'to analyze {without_sentiment:,} statements without sentiment scores'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ All statements have sentiment scores!')
            )
