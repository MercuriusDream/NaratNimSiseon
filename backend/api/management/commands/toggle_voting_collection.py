
from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Toggle voting data collection on/off'

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable voting data collection',
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable voting data collection',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current status of voting data collection',
        )

    def handle(self, *args, **options):
        current_status = getattr(settings, 'ENABLE_VOTING_DATA_COLLECTION', False)
        
        if options['status']:
            status_text = "ENABLED" if current_status else "DISABLED"
            self.stdout.write(
                self.style.SUCCESS(f'🗳️ Voting data collection is currently: {status_text}')
            )
            return
        
        if options['enable'] and options['disable']:
            self.stdout.write(
                self.style.ERROR('❌ Cannot enable and disable at the same time')
            )
            return
        
        if options['enable']:
            self.stdout.write(
                self.style.SUCCESS('✅ Voting data collection ENABLED')
            )
            self.stdout.write(
                'Note: You need to set ENABLE_VOTING_DATA_COLLECTION = True in settings.py'
            )
        elif options['disable']:
            self.stdout.write(
                self.style.SUCCESS('⏸️ Voting data collection DISABLED')
            )
            self.stdout.write(
                'Note: You need to set ENABLE_VOTING_DATA_COLLECTION = False in settings.py'
            )
        else:
            status_text = "ENABLED" if current_status else "DISABLED"
            self.stdout.write(
                f'Current status: {status_text}'
            )
            self.stdout.write(
                'Use --enable, --disable, or --status flags'
            )
