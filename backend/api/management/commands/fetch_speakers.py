
from django.core.management.base import BaseCommand
from django.db import models
from api.tasks import fetch_speaker_details
from api.models import Speaker
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetch and update speaker details from ALLNAMEMBER API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--speaker-name',
            type=str,
            help='Fetch details for a specific speaker by name',
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing speakers with missing details',
        )

    def handle(self, *args, **options):
        speaker_name = options.get('speaker_name')
        update_existing = options.get('update_existing')
        
        if speaker_name:
            self.stdout.write(f'Fetching details for speaker: {speaker_name}')
            speaker = fetch_speaker_details(speaker_name)
            if speaker:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully fetched details for: {speaker.naas_nm} ({speaker.plpt_nm})')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Failed to fetch details for: {speaker_name}')
                )
        
        elif update_existing:
            self.stdout.write('Updating existing speakers with missing details...')
            
            # Find speakers with minimal information (likely temporary records)
            speakers_to_update = Speaker.objects.filter(
                models.Q(plpt_nm='정당정보없음') | 
                models.Q(plpt_nm='') | 
                models.Q(naas_cd__startswith='TEMP_')
            )
            
            updated_count = 0
            for speaker in speakers_to_update:
                self.stdout.write(f'Updating speaker: {speaker.naas_nm}')
                updated_speaker = fetch_speaker_details(speaker.naas_nm)
                if updated_speaker:
                    updated_count += 1
                    self.stdout.write(f'  ✅ Updated: {updated_speaker.naas_nm} ({updated_speaker.plpt_nm})')
                else:
                    self.stdout.write(f'  ❌ Failed to update: {speaker.naas_nm}')
            
            self.stdout.write(
                self.style.SUCCESS(f'Updated {updated_count} speakers')
            )
        
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --speaker-name or --update-existing')
            )
