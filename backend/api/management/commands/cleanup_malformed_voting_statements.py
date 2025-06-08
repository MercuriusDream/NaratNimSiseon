
from django.core.management.base import BaseCommand
from api.models import Statement
from django.db import transaction
import re


class Command(BaseCommand):
    help = 'Remove malformed voting statements that contain long lists of legislator names'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--min-length',
            type=int,
            default=1000,
            help='Minimum character length to consider a statement as potentially malformed (default: 1000)',
        )
        parser.add_argument(
            '--show-samples',
            action='store_true',
            help='Show sample text from detected malformed statements',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        min_length = options.get('min_length', 1000)
        show_samples = options.get('show_samples', False)

        self.stdout.write(
            self.style.SUCCESS('🔍 Searching for malformed voting statements...')
        )

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')

        # Patterns to identify malformed voting statements
        voting_patterns = [
            r'투표\s*의원\s*\(\d+인\)',  # "투표 의원(264인)"
            r'찬성\s*의원\s*\(\d+인\)',  # "찬성 의원(262인)"
            r'반대\s*의원\s*\(\d+인\)',  # "반대 의원(X인)"
            r'기권\s*의원\s*\(\d+인\)',  # "기권 의원(X인)"
        ]

        # Additional criteria for malformed statements
        name_density_patterns = [
            r'[가-힣]{2,4}\s+[가-힣]{2,4}\s+[가-힣]{2,4}',  # Multiple Korean names in sequence
        ]

        malformed_statements = []

        # Find statements that are suspiciously long
        long_statements = Statement.objects.filter(
            text__isnull=False
        ).extra(
            where=["CHAR_LENGTH(text) > %s"],
            params=[min_length]
        )

        self.stdout.write(f'Found {long_statements.count()} statements longer than {min_length} characters')

        for statement in long_statements:
            text = statement.text
            is_malformed = False
            reasons = []

            # Check for voting patterns
            for pattern in voting_patterns:
                if re.search(pattern, text):
                    is_malformed = True
                    reasons.append(f"Contains voting pattern: {pattern}")

            # Check for high density of Korean names
            name_matches = re.findall(name_density_patterns[0], text)
            if len(name_matches) > 20:  # More than 20 name sequences
                is_malformed = True
                reasons.append(f"High name density: {len(name_matches)} name sequences found")

            # Check for repetitive structure (names separated by spaces)
            words = text.split()
            korean_name_count = sum(1 for word in words if re.match(r'^[가-힣]{2,4}$', word))
            if korean_name_count > 50:  # More than 50 Korean names
                is_malformed = True
                reasons.append(f"High Korean name count: {korean_name_count} names")

            # Check for specific malformed patterns from your example
            if '험기금운용계획변경안' in text or '투표 의원(' in text:
                is_malformed = True
                reasons.append("Contains specific malformed voting text patterns")

            if is_malformed:
                malformed_statements.append({
                    'statement': statement,
                    'reasons': reasons,
                    'length': len(text),
                    'preview': text[:200] + '...' if len(text) > 200 else text
                })

        self.stdout.write(f'🚨 Found {len(malformed_statements)} malformed voting statements')

        if malformed_statements and show_samples:
            self.stdout.write('\n📋 Sample malformed statements:')
            for i, item in enumerate(malformed_statements[:5]):  # Show first 5 samples
                statement = item['statement']
                self.stdout.write(f'\n--- Sample {i+1} ---')
                self.stdout.write(f'ID: {statement.id}')
                self.stdout.write(f'Speaker: {statement.speaker.naas_nm}')
                self.stdout.write(f'Session: {statement.session.conf_id}')
                self.stdout.write(f'Length: {item["length"]} characters')
                self.stdout.write(f'Reasons: {", ".join(item["reasons"])}')
                self.stdout.write(f'Preview: {item["preview"]}')

        if malformed_statements:
            self.stdout.write(f'\n🗑️  Preparing to remove {len(malformed_statements)} malformed statements...')
            
            # Group by session for reporting
            sessions_affected = {}
            for item in malformed_statements:
                session_id = item['statement'].session.conf_id
                if session_id not in sessions_affected:
                    sessions_affected[session_id] = 0
                sessions_affected[session_id] += 1

            self.stdout.write(f'📊 Sessions affected: {len(sessions_affected)}')
            for session_id, count in sessions_affected.items():
                self.stdout.write(f'   Session {session_id}: {count} malformed statements')

            if not dry_run:
                with transaction.atomic():
                    statement_ids = [item['statement'].id for item in malformed_statements]
                    deleted_count = Statement.objects.filter(id__in=statement_ids).delete()[0]
                    
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Successfully deleted {deleted_count} malformed statements')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'🔍 DRY RUN: Would delete {len(malformed_statements)} statements')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ No malformed voting statements found!')
            )

        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS('🔍 DRY RUN COMPLETE - Use without --dry-run to apply changes')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ CLEANUP COMPLETE')
            )
