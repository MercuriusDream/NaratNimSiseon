
from django.core.management.base import BaseCommand
from api.models import Speaker
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check assembly member names in local database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count-only',
            action='store_true',
            help='Only show count of members in database',
        )

    def handle(self, *args, **options):
        count_only = options.get('count_only', False)
        
        self.stdout.write(
            self.style.SUCCESS('🔍 Checking assembly member names in local database...')
        )
        
        try:
            # Get all speakers from database
            speakers = Speaker.objects.all()
            speaker_count = speakers.count()
            
            if count_only:
                self.stdout.write(f'📊 Total speakers in database: {speaker_count}')
                return
            
            # Show detailed information
            self.stdout.write(f'📊 Total speakers in database: {speaker_count}')
            
            if speaker_count > 0:
                # Show sample names
                sample_speakers = speakers[:10]
                self.stdout.write('📝 Sample speaker names:')
                for speaker in sample_speakers:
                    party_info = f" ({speaker.current_party.name})" if speaker.current_party else ""
                    self.stdout.write(f'   - {speaker.naas_nm}{party_info}')
                
                if speaker_count > 10:
                    self.stdout.write(f'   ... and {speaker_count - 10} more')
                
                # Check for potential duplicates
                unique_names = set(speakers.values_list('naas_nm', flat=True))
                if len(unique_names) != speaker_count:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ Found {speaker_count - len(unique_names)} potential duplicate names')
                    )
                else:
                    self.stdout.write('✅ All speaker names are unique')
            else:
                self.stdout.write(
                    self.style.WARNING('⚠️ No speakers found in database. Run data collection first.')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error checking assembly members: {e}')
            )
