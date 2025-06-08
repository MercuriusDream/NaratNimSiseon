
from django.core.management.base import BaseCommand
from api.models import Party, Speaker, SpeakerPartyHistory
from django.db import transaction
from django.db.models import Count


class Command(BaseCommand):
    help = 'Fix malformed party names with slashes and consolidate speakers to clean parties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making actual changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN MODE - No changes will be made\n')
        else:
            self.stdout.write('🧹 FIXING malformed party names...\n')

        # Find malformed party names (containing slashes)
        malformed_parties = Party.objects.filter(name__contains='/').order_by('id')
        
        if not malformed_parties.exists():
            self.stdout.write('✅ No malformed party names found!')
            return

        self.stdout.write(f'📋 Found {malformed_parties.count()} malformed party names:')
        
        total_fixed = 0
        total_speakers_moved = 0
        total_parties_removed = 0

        with transaction.atomic():
            for malformed_party in malformed_parties:
                self.stdout.write(f'\n🔄 Processing: "{malformed_party.name}" (ID: {malformed_party.id})')
                
                # Extract the rightmost (most recent) party name
                party_parts = [p.strip() for p in malformed_party.name.split('/') if p.strip()]
                if not party_parts:
                    continue
                    
                target_party_name = party_parts[-1]  # Get the rightmost party
                self.stdout.write(f'   🎯 Target party: "{target_party_name}"')
                
                # Find or create the clean target party
                target_party, created = Party.objects.get_or_create(
                    name=target_party_name,
                    defaults={
                        'description': f'{target_party_name} - 제22대 국회',
                        'assembly_era': 22
                    }
                )
                
                if created:
                    self.stdout.write(f'   ✨ Created clean party: "{target_party_name}"')
                
                # Move all speakers from malformed party to clean party
                speakers_to_move = Speaker.objects.filter(current_party=malformed_party)
                speaker_count = speakers_to_move.count()
                
                if speaker_count > 0:
                    if not dry_run:
                        # Update speakers
                        for speaker in speakers_to_move:
                            speaker.current_party = target_party
                            speaker.plpt_nm = target_party_name  # Clean up plpt_nm too
                            speaker.save()
                            
                            # Update party history
                            SpeakerPartyHistory.objects.filter(speaker=speaker).delete()
                            SpeakerPartyHistory.objects.create(
                                speaker=speaker,
                                party=target_party,
                                order=0,
                                is_current=True
                            )
                        
                        # Delete the malformed party
                        malformed_party.delete()
                        total_parties_removed += 1
                        
                    total_speakers_moved += speaker_count
                    self.stdout.write(f'   ✅ Moved {speaker_count} speakers to "{target_party_name}"')
                    
                    if not dry_run:
                        self.stdout.write(f'   🗑️  Deleted malformed party: "{malformed_party.name}"')
                else:
                    self.stdout.write(f'   ℹ️  No speakers to move, but party is malformed')
                    if not dry_run:
                        malformed_party.delete()
                        total_parties_removed += 1
                        self.stdout.write(f'   🗑️  Deleted empty malformed party: "{malformed_party.name}"')
                
                total_fixed += 1

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write('📊 MALFORMED PARTY CLEANUP SUMMARY:')
        
        if dry_run:
            self.stdout.write(f'   🔍 Would fix {total_fixed} malformed parties')
            self.stdout.write(f'   🔍 Would move {total_speakers_moved} speakers')
            self.stdout.write(f'   🔍 Would remove {total_parties_removed} malformed parties')
            self.stdout.write('\n🔍 This was a DRY RUN - no changes were made')
            self.stdout.write('   Run without --dry-run to apply changes')
        else:
            self.stdout.write(f'   ✅ Fixed {total_fixed} malformed parties')
            self.stdout.write(f'   👥 Moved {total_speakers_moved} speakers')
            self.stdout.write(f'   🗑️  Removed {total_parties_removed} malformed parties')
            self.stdout.write('\n✅ MALFORMED PARTY CLEANUP COMPLETE!')
        
        # Show current party status
        self.stdout.write('\n🏛️  Current party status:')
        clean_parties = Party.objects.annotate(
            member_count=Count('current_members')
        ).filter(member_count__gt=0, name='더불어민주당')
        
        for party in clean_parties:
            self.stdout.write(f'   • {party.name}: {party.member_count} members (ID: {party.id})')
