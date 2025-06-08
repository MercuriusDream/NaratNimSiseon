
from django.core.management.base import BaseCommand
from django.db.models import Count, Avg
from api.models import Party, Speaker, Statement, SpeakerPartyHistory
from collections import defaultdict
import re

class Command(BaseCommand):
    help = 'Fix and organize 22nd Assembly party data properly'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write('🔍 DRY RUN - No changes will be made')
        
        # Define the current 22nd Assembly parties
        current_22nd_parties = {
            '더불어민주당': {
                'description': '더불어민주당 - 제22대 국회 야당',
                'merge_from': ['민주통합당', '더불어민주연합']
            },
            '국민의힘': {
                'description': '국민의힘 - 제22대 국회 여당',
                'merge_from': ['자유한국당', '미래통합당']
            },
            '조국혁신당': {
                'description': '조국혁신당 - 제22대 국회',
                'merge_from': []
            },
            '진보당': {
                'description': '진보당 - 제22대 국회',
                'merge_from': []
            },
            '개혁신당': {
                'description': '개혁신당 - 제22대 국회',
                'merge_from': []
            },
            '새로운미래': {
                'description': '새로운미래 - 제22대 국회',
                'merge_from': ['국민의미래']
            }
        }
        
        # Historical parties that should NOT be in 22nd Assembly
        historical_parties = [
            '민주자유당', '민주정의당', '대한독립촉성국민회', '신민당', 
            '한국당', '바른정당', '국민의당', '정의당' # old version
        ]
        
        self.stdout.write('🏛️ Step 1: Analyzing current Speaker party data...')
        self.stdout.write('   This may take a few minutes for large datasets...')
        
        # Get all speakers and their party information (optimized with select_related)
        speakers = Speaker.objects.select_related('current_party').all()
        party_analysis = defaultdict(lambda: {
            'speakers': [],
            'statement_count': 0,
            'avg_sentiment': 0,
            'final_party_only': []  # Speakers where this is their final party
        })
        
        # Pre-fetch statement counts for all speakers to avoid N+1 queries
        statement_counts = Statement.objects.values('speaker_id').annotate(
            count=Count('id'),
            avg_sentiment=Avg('sentiment_score')
        )
        statement_data = {item['speaker_id']: item for item in statement_counts}
        
        total_speakers = speakers.count()
        processed = 0
        
        for speaker in speakers:
            processed += 1
            if processed % 100 == 0:
                self.stdout.write(f'   Processed {processed}/{total_speakers} speakers...')
                
            party_list = speaker.get_party_list()
            if not party_list:
                continue
                
            # Get the final (most recent) party
            final_party = party_list[-1]
            
            # Get statement data from pre-fetched results
            speaker_data = statement_data.get(speaker.naas_cd, {'count': 0, 'avg_sentiment': 0})
            statement_count = speaker_data['count']
            avg_sentiment = speaker_data['avg_sentiment'] or 0
            
            # Add to all parties in history
            for party in party_list:
                party_analysis[party]['speakers'].append(speaker)
                party_analysis[party]['statement_count'] += statement_count
                
            # Mark as final party member
            party_analysis[final_party]['final_party_only'].append(speaker)
        
        # Display current analysis
        self.stdout.write('\n📊 Current party distribution analysis:')
        for party_name, data in sorted(party_analysis.items(), 
                                     key=lambda x: len(x[1]['final_party_only']), 
                                     reverse=True):
            total_speakers = len(data['speakers'])
            final_only_speakers = len(data['final_party_only'])
            statements = data['statement_count']
            
            if final_only_speakers > 0:  # Only show parties with current members
                self.stdout.write(
                    f'   {party_name}: {final_only_speakers} current members '
                    f'({total_speakers} total historical), {statements} statements'
                )
        
        self.stdout.write('\n🔧 Step 2: Consolidating 22nd Assembly parties...')
        
        consolidated_data = {}
        
        # Process each current party
        for target_party, config in current_22nd_parties.items():
            consolidated_data[target_party] = {
                'speakers': set(),
                'statement_count': 0,
                'description': config['description']
            }
            
            # Add speakers from target party
            if target_party in party_analysis:
                consolidated_data[target_party]['speakers'].update(
                    party_analysis[target_party]['final_party_only']
                )
                consolidated_data[target_party]['statement_count'] += \
                    party_analysis[target_party]['statement_count']
            
            # Merge from specified parties
            for merge_party in config['merge_from']:
                if merge_party in party_analysis:
                    # Only merge speakers whose FINAL party is the merge party
                    consolidated_data[target_party]['speakers'].update(
                        party_analysis[merge_party]['final_party_only']
                    )
                    consolidated_data[target_party]['statement_count'] += \
                        party_analysis[merge_party]['statement_count']
                    
                    self.stdout.write(f'   📝 Merging {merge_party} → {target_party}')
        
        # Handle remaining parties that might be legitimate 22nd Assembly parties
        remaining_parties = {}
        for party_name, data in party_analysis.items():
            final_members = len(data['final_party_only'])
            
            # Skip if already processed or historical
            if (party_name in current_22nd_parties or 
                party_name in historical_parties or
                any(party_name in config['merge_from'] for config in current_22nd_parties.values())):
                continue
            
            # If it has significant current membership, consider it
            if final_members >= 1:
                remaining_parties[party_name] = {
                    'members': final_members,
                    'statements': data['statement_count']
                }
        
        if remaining_parties:
            self.stdout.write('\n❓ Found additional parties with current members:')
            for party, data in remaining_parties.items():
                self.stdout.write(f'   {party}: {data["members"]} members, {data["statements"]} statements')
        
        self.stdout.write('\n📋 Step 3: Final 22nd Assembly party summary:')
        for party_name, data in sorted(consolidated_data.items(), 
                                     key=lambda x: len(x[1]['speakers']), 
                                     reverse=True):
            member_count = len(data['speakers'])
            statement_count = data['statement_count']
            
            if member_count > 0:
                # Calculate average sentiment from already processed data
                total_sentiment = 0
                total_statements = 0
                for speaker in data['speakers']:
                    speaker_data = statement_data.get(speaker.naas_cd, {'count': 0, 'avg_sentiment': 0})
                    if speaker_data['count'] > 0 and speaker_data['avg_sentiment']:
                        total_sentiment += speaker_data['avg_sentiment'] * speaker_data['count']
                        total_statements += speaker_data['count']
                
                avg_sentiment = total_sentiment / total_statements if total_statements > 0 else 0
                
                self.stdout.write(
                    f'   {party_name}: {member_count} 의원, '
                    f'{statement_count} 발언, 평균 감성: {avg_sentiment:.3f}'
                )
        
        if not dry_run:
            self.stdout.write('\n💾 Step 4: Applying changes...')
            
            # Create/update Party objects for 22nd Assembly
            total_parties = len([p for p, d in consolidated_data.items() if len(d['speakers']) > 0])
            processed_parties = 0
            
            for party_name, data in consolidated_data.items():
                if len(data['speakers']) > 0:
                    party, created = Party.objects.get_or_create(
                        name=party_name,
                        defaults={
                            'description': data['description'],
                            'assembly_era': 22
                        }
                    )
                    if created:
                        self.stdout.write(f'   ✨ Created party: {party_name}')
                    else:
                        party.assembly_era = 22
                        party.description = data['description']
                        party.save()
                        self.stdout.write(f'   🔄 Updated party: {party_name}')
                    
                    # Update speaker records in bulk
                    speakers_list = list(data['speakers'])
                    speakers_updated = 0
                    
                    if speakers_list:
                        # Bulk update speakers
                        for speaker in speakers_list:
                            speaker.current_party = party
                            speaker.plpt_nm = party_name
                        
                        # Use bulk_update for better performance
                        Speaker.objects.bulk_update(
                            speakers_list, 
                            ['current_party', 'plpt_nm'], 
                            batch_size=100
                        )
                        
                        # Clear existing party histories for these speakers
                        speaker_ids = [speaker.naas_cd for speaker in speakers_list]
                        SpeakerPartyHistory.objects.filter(speaker__naas_cd__in=speaker_ids).delete()
                        
                        # Create new party histories in bulk
                        party_histories = [
                            SpeakerPartyHistory(
                                speaker=speaker,
                                party=party,
                                order=0,
                                is_current=True
                            ) for speaker in speakers_list
                        ]
                        SpeakerPartyHistory.objects.bulk_create(party_histories, batch_size=100)
                        
                        speakers_updated = len(speakers_list)
                        processed_parties += 1
                        self.stdout.write(f'   👥 Updated {speakers_updated} speakers for {party_name} ({processed_parties}/{total_parties})')
            
            # Clean up historical parties from 22nd Assembly context
            historical_party_objects = Party.objects.filter(
                name__in=historical_parties,
                assembly_era=22
            )
            if historical_party_objects.exists():
                count = historical_party_objects.count()
                historical_party_objects.update(assembly_era=21)  # Move to previous era
                self.stdout.write(f'   🧹 Moved {count} historical parties to era 21')
            
            self.stdout.write('\n✅ 22nd Assembly party organization completed!')
        
        else:
            self.stdout.write('\n🔍 DRY RUN completed - use without --dry-run to apply changes')
