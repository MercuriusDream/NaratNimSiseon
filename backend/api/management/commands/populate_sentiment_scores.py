
from django.core.management.base import BaseCommand
from api.models import Statement
from api.llm_analyzer import LLMAnalyzer
from django.db.models import Q
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Populate sentiment scores for all statements that don\'t have them'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of statements to process in each batch',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without making actual changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-analyze statements that already have sentiment scores',
        )

    def handle(self, *args, **options):
        batch_size = options.get('batch_size', 100)
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        self.stdout.write(
            self.style.SUCCESS('🎯 Starting sentiment score population...')
        )
        
        # Build queryset based on force flag
        if force:
            statements_qs = Statement.objects.filter(
                session__era_co__in=['22', '제22대']
            ).order_by('created_at')
            self.stdout.write('🔄 Force mode: Re-analyzing ALL statements')
        else:
            statements_qs = Statement.objects.filter(
                Q(sentiment_score__isnull=True) | Q(sentiment_score=0.0),
                session__era_co__in=['22', '제22대']
            ).order_by('created_at')
            self.stdout.write('✨ Analyzing statements without sentiment scores')
        
        total_statements = statements_qs.count()
        self.stdout.write(f'📊 Found {total_statements} statements to process')
        
        if total_statements == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ All statements already have sentiment scores!')
            )
            return
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')
            self.stdout.write(f'Would process {total_statements} statements in batches of {batch_size}')
            return
        
        # Initialize LLM analyzer
        try:
            analyzer = LLMAnalyzer()
            self.stdout.write('🤖 LLM Analyzer initialized successfully')
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Failed to initialize LLM Analyzer: {e}')
            )
            return
        
        processed = 0
        errors = 0
        
        # Process in batches
        for i in range(0, total_statements, batch_size):
            batch_statements = statements_qs[i:i + batch_size]
            
            self.stdout.write(
                f'🔄 Processing batch {i//batch_size + 1}/{(total_statements + batch_size - 1)//batch_size} '
                f'(statements {i+1}-{min(i+batch_size, total_statements)})'
            )
            
            for statement in batch_statements:
                try:
                    # Analyze sentiment
                    analysis_result = analyzer.analyze_statement(statement.text)
                    
                    if analysis_result and 'sentiment_score' in analysis_result:
                        statement.sentiment_score = analysis_result['sentiment_score']
                        statement.sentiment_reason = analysis_result.get('sentiment_reason', '')
                        statement.category_analysis = analysis_result.get('category_analysis', '')
                        statement.policy_keywords = analysis_result.get('policy_keywords', '')
                        statement.save()
                        
                        processed += 1
                        
                        if processed % 10 == 0:
                            self.stdout.write(f'   ✅ Processed {processed}/{total_statements} statements')
                    else:
                        self.stdout.write(
                            f'   ⚠️  No sentiment analysis result for statement {statement.id}'
                        )
                        errors += 1
                        
                except Exception as e:
                    self.stdout.write(
                        f'   ❌ Error processing statement {statement.id}: {e}'
                    )
                    errors += 1
                    continue
        
        # Summary
        self.stdout.write('')
        self.stdout.write('📊 Processing Summary:')
        self.stdout.write(f'   Total statements found: {total_statements}')
        self.stdout.write(f'   Successfully processed: {processed}')
        self.stdout.write(f'   Errors: {errors}')
        
        if processed > 0:
            # Show sample of processed sentiment scores
            sample_statements = Statement.objects.filter(
                sentiment_score__isnull=False,
                session__era_co__in=['22', '제22대']
            ).order_by('-updated_at')[:5]
            
            self.stdout.write('')
            self.stdout.write('📈 Sample of recent sentiment scores:')
            for stmt in sample_statements:
                self.stdout.write(
                    f'   {stmt.sentiment_score:.3f} - {stmt.speaker.naas_nm} '
                    f'({stmt.text[:50]}...)'
                )
        
        self.stdout.write('')
        if errors == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ COMPLETE - Successfully populated sentiment scores for {processed} statements!'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  COMPLETE WITH ERRORS - Processed {processed} statements with {errors} errors'
                )
            )
