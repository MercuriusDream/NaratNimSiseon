
from django.core.management.base import BaseCommand
from api.models import Speaker, Statement, Party
from django.db.models import Q
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Aggressively clean up problematic speakers and parties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        self.stdout.write(self.style.SUCCESS('🧹 Starting aggressive cleanup of problematic speakers and parties...'))

        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made')

        # Find all speakers with problematic party assignments
        problematic_speakers = Speaker.objects.filter(
            Q(plpt_nm__icontains='정보없음') |
            Q(plpt_nm__icontains='한나라당') |
            Q(plpt_nm__icontains='대한독립촉성국민회') |
            Q(plpt_nm__icontains='민주자유당') |
            Q(plpt_nm__icontains='민주정의당') |
            Q(plpt_nm__icontains='신민당') |
            Q(current_party__name__icontains='정보없음') |
            Q(current_party__name__icontains='한나라당') |
            Q(current_party__name='정보없음') |
            Q(current_party__name='한나라당')
        ).distinct()

        self.stdout.write(f'Found {problematic_speakers.count()} speakers with problematic party assignments')

        removed_speakers = 0
        fixed_speakers = 0

        for speaker in problematic_speakers:
            self.stdout.write(f'🔄 Processing {speaker.naas_nm}')
            self.stdout.write(f'   Party info: {speaker.plpt_nm}')
            current_party_name = speaker.current_party.name if speaker.current_party else 'None'
            self.stdout.write(f'   Current party: {current_party_name}')

            # Remove 정보없음 speakers completely
            if ('정보없음' in speaker.plpt_nm or 
                (speaker.current_party and '정보없음' in speaker.current_party.name)):
                
                self.stdout.write(f'   🗑️  Removing 정보없음 speaker: {speaker.naas_nm}')
                
                if not dry_run:
                    with transaction.atomic():
                        Statement.objects.filter(speaker=speaker).delete()
                        speaker.delete()
                        removed_speakers += 1
                        self.stdout.write(f'   ✅ Removed {speaker.naas_nm}')
                else:
                    self.stdout.write(f'   🔍 DRY RUN: Would remove {speaker.naas_nm}')
                    removed_speakers += 1
                continue

            # Fix 한나라당 speakers by mapping to 국민의힘
            elif ('한나라당' in speaker.plpt_nm or 
                  (speaker.current_party and '한나라당' in speaker.current_party.name)):
                
                self.stdout.write(f'   🔄 Fixing 한나라당 speaker: {speaker.naas_nm} -> 국민의힘')
                
                if not dry_run:
                    with transaction.atomic():
                        # Get or create 국민의힘 party
                        gukmin_party, created = Party.objects.get_or_create(
                            name='국민의힘',
                            defaults={
                                'description': '국민의힘 - 제22대 국회',
                                'assembly_era': 22
                            }
                        )
                        
                        # Update speaker
                        speaker.current_party = gukmin_party
                        speaker.plpt_nm = '국민의힘'
                        speaker.save()
                        
                        fixed_speakers += 1
                        self.stdout.write(f'   ✅ Fixed {speaker.naas_nm} -> 국민의힘')
                else:
                    self.stdout.write(f'   🔍 DRY RUN: Would fix {speaker.naas_nm} -> 국민의힘')
                    fixed_speakers += 1
                continue

            # Handle other historical parties
            else:
                self.stdout.write(f'   ⚠️  Other historical party for {speaker.naas_nm}: {speaker.plpt_nm}')

        # Clean up problematic party objects
        self.stdout.write('')
        self.stdout.write('🧹 Cleaning up problematic party objects...')
        
        problematic_party_names = ['정보없음', '한나라당', '대한독립촉성국민회', '민주자유당', '민주정의당', '신민당']
        deleted_parties = 0
        
        for party_name in problematic_party_names:
            # Only delete parties that have no speakers assigned
            parties_to_delete = Party.objects.filter(
                name=party_name,
                current_members__isnull=True  # No speakers currently assigned
            )
            
            if parties_to_delete.exists():
                count = parties_to_delete.count()
                self.stdout.write(f'   🗑️  Found {count} unused {party_name} party objects')
                
                if not dry_run:
                    parties_to_delete.delete()
                    deleted_parties += count
                    self.stdout.write(f'   ✅ Deleted {count} {party_name} party objects')
                else:
                    self.stdout.write(f'   🔍 DRY RUN: Would delete {count} {party_name} party objects')
                    deleted_parties += count

        # Summary
        self.stdout.write('')
        self.stdout.write('📊 Cleanup Summary:')
        if dry_run:
            self.stdout.write(f'   Would remove: {removed_speakers} speakers')
            self.stdout.write(f'   Would fix: {fixed_speakers} speakers')
            self.stdout.write(f'   Would delete: {deleted_parties} party objects')
        else:
            self.stdout.write(f'   Removed: {removed_speakers} speakers')
            self.stdout.write(f'   Fixed: {fixed_speakers} speakers')
            self.stdout.write(f'   Deleted: {deleted_parties} party objects')

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.SUCCESS('✅ DRY RUN COMPLETE - Use --dry-run=false to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS('✅ AGGRESSIVE CLEANUP COMPLETE'))
