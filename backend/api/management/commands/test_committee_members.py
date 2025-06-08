
from django.core.management.base import BaseCommand
from api.tasks import fetch_committee_members


class Command(BaseCommand):
    help = 'Test committee member fetching functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--committee',
            type=str,
            default='국회운영위원회',
            help='Committee name to fetch members for (default: 국회운영위원회)',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Enable debug mode',
        )

    def handle(self, *args, **options):
        committee_name = options['committee']
        debug = options.get('debug', False)
        
        self.stdout.write(
            self.style.SUCCESS(f'🔍 Fetching committee members for: {committee_name}')
        )
        
        try:
            members = fetch_committee_members(committee_name, debug=debug)
            
            if members:
                self.stdout.write(f'✅ Found {len(members)} committee members:')
                for i, member in enumerate(members, 1):
                    self.stdout.write(
                        f'  {i}. {member["name"]} ({member["party"]}) - {member["position"]}'
                    )
                    if member.get('constituency'):
                        self.stdout.write(f'     📍 {member["constituency"]}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️ No members found for committee: {committee_name}')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error fetching committee members: {e}')
            )
