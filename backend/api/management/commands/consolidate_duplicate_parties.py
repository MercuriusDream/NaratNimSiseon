
from django.core.management.base import BaseCommand
from api.models import Party, Speaker, Statement, SpeakerPartyHistory
from django.db.models import Count
from django.db import transaction
from collections import defaultdict


class Command(BaseCommand):
    help = 'Consolidate ALL duplicate parties under the same name into ONE party record'

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
            self.stdout.write('🔧 CONSOLIDATING duplicate parties...\n')

        # Step 1: Find all duplicate party names
        duplicate_parties = Party.objects.values('name').annotate(
            count=Count('id')
        ).filter(count__gt=1).order_by('name')

        if not duplicate_parties.exists():
            self.stdout.write('✅ No duplicate parties found!')
            return

        total_consolidated = 0
        total_speakers_updated = 0
        total_history_updated = 0

        self.stdout.write(f'📊 Found {duplicate_parties.count()} party names with duplicates:')
        
        for party_info in duplicate_parties:
            party_name = party_info['name']
            duplicate_count = party_info['count']
            
            self.stdout.write(f'\n🔄 Processing "{party_name}" ({duplicate_count} duplicates)')
            
            # Get all parties with this name, ordered by ID (keep the first one)
            parties_with_same_name = Party.objects.filter(name=party_name).order_by('id')
            
            if parties_with_same_name.count() <= 1:
                continue
            
            # Keep the first party (lowest ID) as the primary
            primary_party = parties_with_same_name.first()
            duplicate_parties_to_merge = parties_with_same_name[1:]
            
            self.stdout.write(f'   📌 Keeping primary party: ID {primary_party.id}')
            self.stdout.write(f'   🗑️  Merging {duplicate_parties_to_merge.count()} duplicates')
            
            if not dry_run:
                with transaction.atomic():
                    speakers_updated = 0
                    history_updated = 0
                    
                    # Update all speakers pointing to duplicate parties
                    for duplicate_party in duplicate_parties_to_merge:
                        # Update speakers' current_party
                        speakers_to_update = Speaker.objects.filter(current_party=duplicate_party)
                        speakers_count = speakers_to_update.count()
                        if speakers_count > 0:
                            speakers_to_update.update(current_party=primary_party)
                            speakers_updated += speakers_count
                            self.stdout.write(f'      ✅ Updated {speakers_count} speakers from party ID {duplicate_party.id}')
                        
                        # Update speaker party history
                        history_to_update = SpeakerPartyHistory.objects.filter(party=duplicate_party)
                        history_count = history_to_update.count()
                        if history_count > 0:
                            history_to_update.update(party=primary_party)
                            history_updated += history_count
                            self.stdout.write(f'      ✅ Updated {history_count} party history records from party ID {duplicate_party.id}')
                        
                        # Delete the duplicate party
                        self.stdout.write(f'      🗑️  Deleting duplicate party ID {duplicate_party.id}')
                        duplicate_party.delete()
                    
                    total_speakers_updated += speakers_updated
                    total_history_updated += history_updated
                    total_consolidated += duplicate_parties_to_merge.count()
                    
                    self.stdout.write(f'   ✅ Consolidated "{party_name}": {speakers_updated} speakers, {history_updated} history records')
            else:
                # Dry run - just count what would be updated
                speakers_count = 0
                history_count = 0
                for duplicate_party in duplicate_parties_to_merge:
                    speakers_count += Speaker.objects.filter(current_party=duplicate_party).count()
                    history_count += SpeakerPartyHistory.objects.filter(party=duplicate_party).count()
                
                total_speakers_updated += speakers_count
                total_history_updated += history_count
                total_consolidated += duplicate_parties_to_merge.count()
                
                self.stdout.write(f'   🔍 Would consolidate "{party_name}": {speakers_count} speakers, {history_count} history records')

        # Final summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write('📊 CONSOLIDATION SUMMARY:')
        self.stdout.write(f'   🎯 Party duplicates consolidated: {total_consolidated}')
        self.stdout.write(f'   👥 Speaker records updated: {total_speakers_updated}')
        self.stdout.write(f'   📚 History records updated: {total_history_updated}')
        
        if dry_run:
            self.stdout.write('\n🔍 This was a DRY RUN - no changes were made')
            self.stdout.write('   Run without --dry-run to apply changes')
        else:
            self.stdout.write('\n✅ ALL DUPLICATE PARTIES CONSOLIDATED!')
        
        # Show final party count
        final_party_count = Party.objects.count()
        self.stdout.write(f'\n📈 Final party count: {final_party_count}')
        
        # Show top parties by member count
        self.stdout.write('\n🏛️  Top parties by member count:')
        top_parties = Party.objects.annotate(
            member_count=Count('current_members')
        ).filter(member_count__gt=0).order_by('-member_count')[:10]
        
        for party in top_parties:
            self.stdout.write(f'   • {party.name}: {party.member_count} members')
