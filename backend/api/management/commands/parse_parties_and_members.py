
from django.core.management.base import BaseCommand
from api.tasks import fetch_party_membership_data, fetch_additional_data_nepjpxkkabqiqpbvk, is_celery_available
from api.models import Party, Speaker
import requests
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Parse and fetch all party and member data comprehensively'

    def add_arguments(self, parser):
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Run in debug mode (no database writes)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch of existing data',
        )
        parser.add_argument(
            '--parties-only',
            action='store_true',
            help='Only fetch party data',
        )
        parser.add_argument(
            '--members-only',
            action='store_true',
            help='Only fetch member data',
        )

    def handle(self, *args, **options):
        debug = options['debug']
        force = options['force']
        parties_only = options['parties_only']
        members_only = options['members_only']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting comprehensive party and member parsing...')
        )
        
        if not members_only:
            self.stdout.write('📊 Fetching party data...')
            try:
                if is_celery_available() and not debug:
                    fetch_party_membership_data.delay(debug=debug)
                    self.stdout.write('✅ Party data collection task started (async)')
                else:
                    fetch_party_membership_data(debug=debug)
                    self.stdout.write('✅ Party data collection completed')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error fetching party data: {e}')
                )
        
        if not parties_only:
            self.stdout.write('👥 Fetching additional party and member data...')
            try:
                if is_celery_available() and not debug:
                    fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force, debug=debug)
                    self.stdout.write('✅ Additional data collection task started (async)')
                else:
                    fetch_additional_data_nepjpxkkabqiqpbvk(force=force, debug=debug)
                    self.stdout.write('✅ Additional data collection completed')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error fetching additional data: {e}')
                )
        
        # Display current status
        self.stdout.write('\n📈 Current Database Status:')
        self.stdout.write(f'   Parties: {Party.objects.count()}')
        self.stdout.write(f'   Members/Speakers: {Speaker.objects.count()}')
        
        if Party.objects.exists():
            self.stdout.write('\n🏛️ Parties in Database:')
            for party in Party.objects.all():
                member_count = Speaker.objects.filter(plpt_nm=party.name).count()
                self.stdout.write(f'   • {party.name}: {member_count} members')
        
        self.stdout.write(
            self.style.SUCCESS('\n✅ Party and member parsing completed!')
        )
