
from django.core.management.base import BaseCommand
from api.tasks import fetch_party_membership_data


class Command(BaseCommand):
    help = 'Fetch party membership data from Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Run in debug mode (no database writes)',
        )

    def handle(self, *args, **options):
        debug = options['debug']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting party membership data collection (debug={debug})...'
            )
        )
        
        try:
            # Run synchronously for management command
            fetch_party_membership_data(debug=debug)
            self.stdout.write(
                self.style.SUCCESS('Party membership data collection completed!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during party data collection: {e}')
            )
