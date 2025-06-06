
from django.core.management.base import BaseCommand
from api.tasks import fetch_additional_data_nepjpxkkabqiqpbvk, is_celery_available


class Command(BaseCommand):
    help = 'Fetch additional data from nepjpxkkabqiqpbvk API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch of existing data',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it',
        )

    def handle(self, *args, **options):
        force = options.get('force')
        debug = options.get('debug')
        
        if debug:
            self.stdout.write(
                self.style.SUCCESS('🐛 Starting DEBUG nepjpxkkabqiqpbvk data collection...')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('🚀 Starting nepjpxkkabqiqpbvk data collection...')
            )
        
        try:
            if is_celery_available():
                self.stdout.write('🚀 Using Celery for async processing')
                fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force, debug=debug)
                self.stdout.write(
                    self.style.SUCCESS('✅ nepjpxkkabqiqpbvk data collection task started!')
                )
            else:
                self.stdout.write('🔄 Running synchronously (Celery not available)')
                fetch_additional_data_nepjpxkkabqiqpbvk(force=force, debug=debug)
                self.stdout.write(
                    self.style.SUCCESS('✅ nepjpxkkabqiqpbvk data collection completed!')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error starting nepjpxkkabqiqpbvk collection: {e}')
            )
