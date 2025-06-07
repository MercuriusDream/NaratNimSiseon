
from django.core.management.base import BaseCommand
from api.tasks import fetch_continuous_sessions


class Command(BaseCommand):
    help = 'Refresh all data from National Assembly APIs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force complete data refresh (all historical data)',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Run in debug mode with detailed logging',
        )

    def handle(self, *args, **options):
        force = options['force']
        debug = options['debug']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting data refresh (force={force}, debug={debug})...'
            )
        )
        
        try:
            # Run the data collection task
            fetch_continuous_sessions(force=force, debug=debug)
            
            self.stdout.write(
                self.style.SUCCESS('Data refresh completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Data refresh failed: {e}')
            )
            raise
