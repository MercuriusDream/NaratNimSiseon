from django.core.management.base import BaseCommand
from api.tasks import fetch_additional_data_nepjpxkkabqiqpbvk, is_celery_available
from api.models import Speaker
import requests
import json
from django.conf import settings
import logging
import os
from api.models import Party, SpeakerPartyHistory

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Parse and sync party and member data from the Assembly API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh of existing data',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Debug mode: print data instead of storing it',
        )
        parser.add_argument(
            '--parties-only',
            action='store_true',
            help='Only create Party objects from existing Speaker data',
        )
        parser.add_argument(
            '--create-parties',
            action='store_true',
            help='Create Party objects from existing Speaker data',
        )
        parser.add_argument(
            '--update-relationships',
            action='store_true',
            help='Update Speaker-Party relationships using party history',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        debug = options.get('debug', False)
        parties_only = options.get('parties_only', False)
        create_parties = options.get('create_parties', False)
        update_relationships = options.get('update_relationships', False)

        if parties_only:
            self.stdout.write(
                '🏛️ Creating Party objects from existing Speaker data...')
            self.create_parties_from_speakers()
            self.stdout.write(
                self.style.SUCCESS('✅ Party creation completed!'))
            return

        self.stdout.write('🏛️ Starting party and member data parsing...')

        if debug:
            self.stdout.write(
                '🐛 DEBUG mode: Will print data instead of storing')

        # Fetch member data from ALLNAMEMBER API
        self.fetch_and_parse_members(force=force, debug=debug)

        # Fetch additional party data
        self.stdout.write('📊 Fetching additional party data...')
        if is_celery_available():
            fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=force,
                                                          debug=debug)
        else:
            fetch_additional_data_nepjpxkkabqiqpbvk(force=force, debug=debug)

        self.stdout.write(
            self.style.SUCCESS('✅ Party and member data parsing completed!'))

        if create_parties:
            self.stdout.write(
                '🏛️ Creating Party objects from existing Speaker data...')
            self.create_parties_from_existing_speakers()

        if update_relationships:
            self.stdout.write('🔗 Updating Speaker-Party relationships...')
            self.update_speaker_party_relationships()

        if not create_parties and not update_relationships:
            # Default: do both
            self.stdout.write(
                '🏛️ Creating Party objects from existing Speaker data...')
            self.create_parties_from_existing_speakers()
            self.stdout.write('🔗 Updating Speaker-Party relationships...')
            self.update_speaker_party_relationships()
            self.stdout.write(
                '📊 Fetching additional party data from Assembly API...')
            self.fetch_party_data_from_api()

    def fetch_and_parse_members(self, force=False, debug=False):
        """Fetch all assembly members from ALLNAMEMBER API"""
        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
            return

        url = "https://open.assembly.go.kr/portal/openapi/ALLNAMEMBER"

        # Fetch data with pagination
        all_members = []
        page = 1
        page_size = 100

        while True:
            params = {
                "KEY": settings.ASSEMBLY_API_KEY,
                "Type": "json",
                "pIndex": page,
                "pSize": page_size
            }

            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                members_data = []
                if 'ALLNAMEMBER' in data and len(data['ALLNAMEMBER']) > 1:
                    members_data = data['ALLNAMEMBER'][1].get('row', [])

                if not members_data:
                    break

                all_members.extend(members_data)
                self.stdout.write(
                    f'📥 Fetched page {page}: {len(members_data)} members')

                if len(members_data) < page_size:
                    break

                page += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error fetching page {page}: {e}'))
                break

        self.stdout.write(f'📊 Total members fetched: {len(all_members)}')

        if debug:
            self.stdout.write('🐛 DEBUG: Sample member data:')
            if all_members:
                self.stdout.write(
                    json.dumps(all_members[0], indent=2, ensure_ascii=False))
            return

        # Process and save members
        created_count = 0
        updated_count = 0
        batch_size = 50  # Process in smaller batches
        total_members = len(all_members)

        self.stdout.write(
            f'📝 Processing {total_members} members in batches of {batch_size}...'
        )

        # Track unique parties to create Party objects
        unique_parties = set()

        for i in range(0, total_members, batch_size):
            batch = all_members[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_members + batch_size - 1) // batch_size

            self.stdout.write(
                f'⚙️  Processing batch {batch_num}/{total_batches} ({len(batch)} members)...'
            )

            for member_data in batch:
                try:
                    naas_cd = member_data.get('NAAS_CD')
                    if not naas_cd:
                        continue

                    party_name = member_data.get('PLPT_NM', '정당정보없음').strip()

                    # Handle party names with "/" - use the newest (last) party
                    if party_name and '/' in party_name:
                        party_name = party_name.split('/')[-1].strip()

                    # Extract all parties from party history for unique_parties tracking
                    original_party_name = member_data.get('PLPT_NM',
                                                          '정당정보없음').strip()
                    if original_party_name and original_party_name != '정당정보없음':
                        party_list = [
                            p.strip() for p in original_party_name.split('/')
                            if p.strip()
                        ]
                        unique_parties.update(party_list)
                    # Handle null values with safe defaults
                    naas_ch_nm = member_data.get('NAAS_CH_NM')
                    if naas_ch_nm is None or naas_ch_nm == '':
                        naas_ch_nm = '정보없음'

                    # Parse fields as required by new schema
                    original_party_name = member_data.get('PLPT_NM',
                                                          '정당정보없음').strip()
                    party_list = [p.strip() for p in original_party_name.split('/') if p.strip()] if original_party_name and original_party_name != '정당정보없음' else []
                    current_party = party_list[-1] if party_list else '정당정보없음'

                    # Split fields as lists
                    elecd_nm = [
                        e.strip()
                        for e in (member_data.get('ELECD_NM') or '').split('/')
                        if e.strip()
                    ]
                    elecd_div_nm = [
                        e.strip() for e in (
                            member_data.get('ELECD_DIV_NM') or '').split('/')
                        if e.strip()
                    ]
                    cmit_nm = [
                        c.strip()
                        for c in (member_data.get('CMIT_NM') or '').split(',')
                        if c.strip()
                    ]
                    blng_cmit_nm = [
                        c.strip() for c in (
                            member_data.get('BLNG_CMIT_NM') or '').split(',')
                        if c.strip()
                    ]

                    # GTELT_ERACO: extract numbers from strings like '제12대, 제14대, 제15대'
                    import re
                    gtelt_eraco_raw = member_data.get('GTELT_ERACO', '')
                    gtelt_eraco = [
                        int(num)
                        for num in re.findall(r'제(\d+)대', gtelt_eraco_raw)
                    ] if gtelt_eraco_raw else []

                    # RLCT_DIV_NM: extract integer from string like '3선'
                    rlct_div_nm_raw = member_data.get('RLCT_DIV_NM', '')
                    rlct_div_nm_int = int(
                        re.sub(
                            r'[^0-9]', '',
                            rlct_div_nm_raw)) if rlct_div_nm_raw and re.search(
                                r'\d+', rlct_div_nm_raw) else None

                    speaker, created = Speaker.objects.update_or_create(
                        naas_cd=naas_cd,
                        defaults={
                            'naas_nm': member_data.get('NAAS_NM', '정보없음'),
                            'naas_ch_nm': naas_ch_nm,
                            'plpt_nm': current_party,
                            'elecd_nm': elecd_nm,
                            'elecd_div_nm': elecd_div_nm,
                            'cmit_nm': cmit_nm,
                            'blng_cmit_nm': blng_cmit_nm,
                            'gtelt_eraco': gtelt_eraco,
                            'era_int':
                            gtelt_eraco[-1] if gtelt_eraco else None,
                            'nth_term': rlct_div_nm_int,
                            'rlct_div_nm': rlct_div_nm_raw,
                            'ntr_div': member_data.get('NTR_DIV', '정보없음'),
                            'naas_pic': member_data.get('NAAS_PIC', '')
                        })
                    # Optionally, store party history for later use
                    speaker.party_history_cache = party_list  # Not saved to DB, just for batch use

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ Error processing member {member_data.get("NAAS_NM", "Unknown")}: {e}'
                        ))
                    continue

            # Show progress after each batch
            self.stdout.write(
                f'✅ Batch {batch_num} complete. Progress: {created_count} created, {updated_count} updated'
            )

            # Small delay to prevent database overload
            import time
            time.sleep(0.1)

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Members processed: {created_count} created, {updated_count} updated'
            ))

        # Create Party objects from clean API data and existing speaker data
        self.fetch_and_create_parties(force=force, debug=debug)

        # Process speaker party histories
        self.process_speaker_party_histories()

    def create_parties_from_speakers(self):
        """Create Party objects from clean API data and process speaker histories"""
        self.stdout.write('📝 Creating Party objects from Assembly API data...')
        self.fetch_and_create_parties(force=False, debug=False)

        # Also create parties from existing speaker data
        self.stdout.write(
            '📝 Creating Party objects from existing Speaker data...')
        self.create_parties_from_existing_speakers()

        # Process speaker party histories
        self.process_speaker_party_histories()

    def fetch_and_create_parties(self, force=False, debug=False):
        """Fetch clean party data from Assembly APIs and create Party objects"""
        from api.models import Party

        if not hasattr(settings,
                       'ASSEMBLY_API_KEY') or not settings.ASSEMBLY_API_KEY:
            self.stdout.write(
                self.style.ERROR('❌ ASSEMBLY_API_KEY not configured'))
            return

        # Try current party composition first (22nd assembly)
        current_parties = self.fetch_current_parties()

        # Try historical party data (21st assembly and below)
        historical_parties = self.fetch_historical_parties()

        # Combine and deduplicate
        all_parties = {}

        # Add current parties
        for party in current_parties:
            party_name = party.get('POLY_NM', '').strip()
            if party_name and party_name not in ['비교섭단체', '합계']:
                all_parties[party_name] = {
                    'name': party_name,
                    'description':
                    f'{party_name} - 현재 의석수: {party.get("N3", 0)}석',
                    'current_seats': party.get('N3', 0)
                }

        # Add historical parties
        for party in historical_parties:
            party_name = party.get('PLPT_NM', '').strip()
            if party_name and party_name not in [
                    '합계'
            ] and party_name not in all_parties:
                all_parties[party_name] = {
                    'name': party_name,
                    'description': f'{party_name} - 제21대 국회',
                    'current_seats': 0
                }

        if debug:
            self.stdout.write('🐛 DEBUG: Party data to create:')
            for party_name, party_data in all_parties.items():
                self.stdout.write(f'  - {party_name}: {party_data}')
            return

        # Create Party objects
        party_created_count = 0
        party_updated_count = 0

        self.stdout.write(
            f'📝 Creating/updating {len(all_parties)} parties from API data...')

        for party_name, party_data in all_parties.items():
            try:
                party, created = Party.objects.update_or_create(
                    name=party_name,
                    defaults={
                        'description': party_data['description'],
                        'slogan': '',
                        'logo_url': ''
                    })

                if created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')
                else:
                    party_updated_count += 1
                    self.stdout.write(f'🔄 Updated party: {party_name}')

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error creating/updating party {party_name}: {e}'))
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Parties processed: {party_created_count} created, {party_updated_count} updated'
            ))

    def process_speaker_party_histories(self):
        """Process all speakers and create party history records"""
        from api.models import Party, SpeakerPartyHistory

        self.stdout.write('🔄 Processing speaker party histories...')

        speakers = Speaker.objects.all()
        processed_count = 0

        for speaker in speakers:
            try:
                party_list = speaker.get_party_list()
                if not party_list:
                    continue

                # Clear existing history for this speaker
                SpeakerPartyHistory.objects.filter(speaker=speaker).delete()

                # Create party history records
                for order, party_name in enumerate(party_list):
                    try:
                        party, created = Party.objects.get_or_create(
                            name=party_name,
                            defaults={'description': f'{party_name} - 자동 생성됨'})

                        is_current = (order == len(party_list) - 1
                                      )  # Last party is current

                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=party,
                            order=order,
                            is_current=is_current)

                        # Set current party
                        if is_current:
                            speaker.current_party = party
                            speaker.save(update_fields=['current_party'])

                    except Exception as e:
                        self.stdout.write(
                            f'⚠️  Warning: Could not process party "{party_name}" for {speaker.naas_nm}: {e}'
                        )
                        continue

                processed_count += 1

                if processed_count % 50 == 0:
                    self.stdout.write(
                        f'🔄 Processed {processed_count} speakers...')

            except Exception as e:
                self.stdout.write(
                    f'❌ Error processing speaker {speaker.naas_nm}: {e}')
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Speaker party histories processed: {processed_count} speakers'
            ))

    def create_parties_from_existing_speakers(self):
        """Create Party objects from existing Speaker data party histories"""
        from api.models import Party

        unique_parties = set()

        # Get all unique parties from speaker data
        speakers = Speaker.objects.all()
        for speaker in speakers:
            party_list = speaker.get_party_list()
            unique_parties.update(party_list)

        self.stdout.write(
            f'📝 Creating Party objects for {len(unique_parties)} unique parties...'
        )

        party_created_count = 0

        for party_name in unique_parties:
            if not party_name or party_name == '정당정보없음':
                continue

            try:
                party, created = Party.objects.get_or_create(
                    name=party_name,
                    defaults={
                        'description': f'{party_name} - 국회의원 데이터에서 추출',
                        'slogan': '',
                        'logo_url': ''
                    })

                if created:
                    party_created_count += 1
                    self.stdout.write(f'✨ Created party: {party_name}')

            except Exception as e:
                self.stdout.write(f'⚠️ Error creating party {party_name}: {e}')
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Created {party_created_count} new parties from speaker data'
            ))

    def fetch_current_parties(self):
        """Fetch current party composition from nepjpxkkabqiqpbvk API"""
        url = "https://open.assembly.go.kr/portal/openapi/nepjpxkkabqiqpbvk"
        params = {"KEY": settings.ASSEMBLY_API_KEY, "Type": "json"}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'nepjpxkkabqiqpbvk' in data and len(
                    data['nepjpxkkabqiqpbvk']) > 1:
                parties = data['nepjpxkkabqiqpbvk'][1].get('row', [])
                self.stdout.write(f'📥 Fetched {len(parties)} current parties')
                return parties

        except Exception as e:
            self.stdout.write(
                f'⚠️  Warning: Could not fetch current parties: {e}')

        return []

    def fetch_historical_parties(self):
        """Fetch historical party data from nedjqrnlavrvcycue API"""
        url = "https://open.assembly.go.kr/portal/openapi/nedjqrnlavrvcycue"
        params = {
            "KEY": settings.ASSEMBLY_API_KEY,
            "ORD_NO": "제21대",
            "Type": "json"
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'nedjqrnlavrvcycue' in data and len(
                    data['nedjqrnlavrvcycue']) > 1:
                parties = data['nedjqrnlavrvcycue'][1].get('row', [])
                self.stdout.write(
                    f'📥 Fetched {len(parties)} historical parties (21st assembly)'
                )
                return parties

        except Exception as e:
            self.stdout.write(
                f'⚠️  Warning: Could not fetch historical parties: {e}')

        return []

    def fetch_party_data_from_api(self):
        """Fetch party data from Assembly API based on era"""
        assembly_api_key = os.getenv('ASSEMBLY_API_KEY')
        if not assembly_api_key:
            self.stdout.write(
                '⚠️ ASSEMBLY_API_KEY not found in environment variables')
            return

        # For 22대 (current), use nepjpxkkabqiqpbvk
        self.stdout.write(
            '📊 Fetching 22대 party data from nepjpxkkabqiqpbvk API...')
        try:
            url_22 = f"https://open.assembly.go.kr/portal/openapi/nepjpxkkabqiqpbvk?KEY={assembly_api_key}&Type=json"
            response = requests.get(url_22, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'nepjpxkkabqiqpbvk' in data and len(
                    data['nepjpxkkabqiqpbvk']) > 1:
                parties_data = data['nepjpxkkabqiqpbvk'][1].get('row', [])
                self.stdout.write(
                    f'📊 Found {len(parties_data)} parties for 22대')

                for party_data in parties_data:
                    party_name = party_data.get('POLY_NM', '').strip()
                    if party_name:
                        try:
                            party, created = Party.objects.get_or_create(
                                name=party_name,
                                defaults={
                                    'description':
                                    f'22대 국회 정당 - 의석수: {party_data.get("N3", "정보없음")}',
                                    'slogan':
                                    f'의석 점유율: {party_data.get("N4", "정보없음")}%'
                                })
                            if created:
                                self.stdout.write(
                                    f'✨ Created 22대 party: {party_name}')
                            else:
                                # Update existing party with additional info
                                if not party.description:
                                    party.description = f'22대 국회 정당 - 의석수: {party_data.get("N3", "정보없음")}'
                                    party.save()
                                    self.stdout.write(
                                        f'🔄 Updated party info: {party_name}')
                        except Exception as e:
                            self.stdout.write(
                                f'⚠️ Error processing 22대 party {party_name}: {e}'
                            )

        except Exception as e:
            self.stdout.write(f'❌ Error fetching 22대 party data: {e}')

        # For 21대 and below, use nedjqrnlavrvcycue
        self.stdout.write(
            '📊 Fetching 21대 party data from nedjqrnlavrvcycue API...')
        try:
            url_21 = f"https://open.assembly.go.kr/portal/openapi/nedjqrnlavrvcycue?KEY={assembly_api_key}&ORD_NO=제21대&type=json"
            response = requests.get(url_21, timeout=30)
            response.raise_for_status()

            data = response.json()
            if 'nedjqrnlavrvcycue' in data and len(
                    data['nedjqrnlavrvcycue']) > 1:
                parties_data = data['nedjqrnlavrvcycue'][1].get('row', [])
                self.stdout.write(
                    f'📊 Found {len(parties_data)} parties for 21대')

                for party_data in parties_data:
                    party_name = party_data.get('PLPT_NM', '').strip()
                    if party_name and party_name != '합계':  # Skip total row
                        try:
                            party, created = Party.objects.get_or_create(
                                name=party_name,
                                defaults={
                                    'description': f'21대 국회 정당',
                                    'slogan': ''
                                })
                            if created:
                                self.stdout.write(
                                    f'✨ Created 21대 party: {party_name}')

                            # Update with specific 21대 info if available
                            member_count = party_data.get('PLMST_PSNCNT')
                            proportional_count = party_data.get('PRPRR_PSNCNT')
                            if member_count or proportional_count:
                                additional_info = []
                                if member_count:
                                    additional_info.append(
                                        f'지역구: {member_count}명')
                                if proportional_count:
                                    additional_info.append(
                                        f'비례대표: {proportional_count}명')

                                if additional_info and not party.description.endswith(
                                        '정당'):
                                    party.description += f' - {", ".join(additional_info)}'
                                    party.save()
                                    self.stdout.write(
                                        f'🔄 Updated 21대 party info: {party_name}'
                                    )

                        except Exception as e:
                            self.stdout.write(
                                f'⚠️ Error processing 21대 party {party_name}: {e}'
                            )

        except Exception as e:
            self.stdout.write(f'❌ Error fetching 21대 party data: {e}')

    def update_speaker_party_relationships(self):
        """Update Speaker-Party relationships using party history from plpt_nm field"""
        from api.models import Party, SpeakerPartyHistory

        speakers = Speaker.objects.all()
        processed_count = 0

        self.stdout.write(
            f'🔗 Processing {speakers.count()} speakers for party relationships...'
        )

        for speaker in speakers:
            try:
                # Clear existing party history for this speaker
                SpeakerPartyHistory.objects.filter(speaker=speaker).delete()

                # Get party list from plpt_nm field
                party_list = speaker.get_party_list()

                if not party_list:
                    self.stdout.write(
                        f'⚠️ No party history found for {speaker.naas_nm}')
                    continue

                # Create party history records
                for order, party_name in enumerate(party_list):
                    try:
                        # Get or create the party
                        party, created = Party.objects.get_or_create(
                            name=party_name,
                            defaults={
                                'description': f'{party_name} - 국회의원 데이터에서 추출',
                                'slogan': '',
                                'logo_url': ''
                            })

                        # Determine if this is the current party (last in the list)
                        is_current = (order == len(party_list) - 1)

                        # Create party history record
                        SpeakerPartyHistory.objects.create(
                            speaker=speaker,
                            party=party,
                            order=order,
                            is_current=is_current)

                        # Set current party
                        if is_current:
                            speaker.current_party = party
                            speaker.save(update_fields=['current_party'])

                    except Exception as e:
                        self.stdout.write(
                            f'⚠️ Warning: Could not process party "{party_name}" for {speaker.naas_nm}: {e}'
                        )
                        continue

                processed_count += 1

                if processed_count % 50 == 0:
                    self.stdout.write(
                        f'🔄 Processed {processed_count} speakers...')

            except Exception as e:
                self.stdout.write(
                    f'❌ Error processing speaker {speaker.naas_nm}: {e}')
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Updated party relationships for {processed_count} speakers'
            ))
