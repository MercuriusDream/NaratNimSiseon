from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Session, Bill, Speaker, Statement, Party
from .serializers import SessionSerializer, StatementCreateSerializer # Added imports
from django.utils import timezone
import datetime


class ModelCreationTests(APITestCase):
    def test_create_party(self):
        Party.objects.create(name="Test Party")
        self.assertEqual(Party.objects.count(), 1)

    def test_create_session(self):
        Session.objects.create(
            conf_id="test_conf_id",
            era_co="21",
            sess="300",
            dgr="1",
            conf_dt=datetime.date.today(),
            conf_knd="본회의",
            cmit_nm="본회의",
            bg_ptm=datetime.time(10, 0, 0),
            ed_ptm=datetime.time(12, 0, 0),
            down_url="http://example.com/pdf"
        )
        self.assertEqual(Session.objects.count(), 1)

    def test_create_speaker(self):
        Speaker.objects.create(
            naas_cd="test_naas_cd",
            naas_nm="홍길동",
            plpt_nm="미래당",
            elecd_nm="서울 강남갑",
            elecd_div_nm="지역구",
            rlct_div_nm="초선",
            gtelt_eraco="21",
            ntr_div="남"
        )
        self.assertEqual(Speaker.objects.count(), 1)

    def test_create_bill(self):
        session = Session.objects.create(
            conf_id="test_conf_id_for_bill",
            era_co="21",
            sess="301",
            dgr="2",
            conf_dt=datetime.date.today(),
            conf_knd="위원회",
            cmit_nm="법제사법위원회",
            bg_ptm=datetime.time(14, 0, 0),
            ed_ptm=datetime.time(16, 0, 0),
            down_url="http://example.com/pdf_bill_session"
        )
        Bill.objects.create(
            bill_id="test_bill_id",
            session=session,
            bill_nm="테스트 법안",
            link_url="http://example.com/bill"
        )
        self.assertEqual(Bill.objects.count(), 1)

    def test_create_statement(self):
        session = Session.objects.create(
            conf_id="test_conf_id_for_statement",
            era_co="21",
            sess="302",
            dgr="3",
            conf_dt=datetime.date.today(),
            conf_knd="정기회의",
            cmit_nm="본회의",
            bg_ptm=datetime.time(9, 0, 0),
            ed_ptm=datetime.time(11, 0, 0),
            down_url="http://example.com/pdf_statement_session"
        )
        speaker = Speaker.objects.create(
            naas_cd="test_naas_cd_stmt", # Shortened to fit max_length
            naas_nm="김철수",
            plpt_nm="정의당",
            elecd_nm="비례대표",
            elecd_div_nm="비례대표",
            rlct_div_nm="재선",
            gtelt_eraco="20,21",
            ntr_div="남"
        )
        bill = Bill.objects.create(
            bill_id="test_bill_id_for_statement",
            session=session,
            bill_nm="중요 법안",
            link_url="http://example.com/important_bill"
        )
        Statement.objects.create(
            session=session,
            speaker=speaker,
            bill=bill,
            text="이 법안에 찬성합니다.",
            sentiment_score=0.8,
            sentiment_reason="국민들의 삶에 긍정적인 영향을 줄 것으로 기대됩니다."
        )
        self.assertEqual(Statement.objects.count(), 1)


from django.contrib.auth.models import User


class PartyAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.login(username='testuser', password='testpassword')

    def test_list_parties(self):
        Party.objects.create(name="Party A", slogan="Slogan A")
        Party.objects.create(name="Party B", slogan="Slogan B")

        url = reverse('party-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Assuming pagination is enabled

    def test_retrieve_party(self):
        party = Party.objects.create(name="Party C", slogan="Slogan C")

        url = reverse('party-detail', kwargs={'pk': party.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], party.name)

    def test_create_party_api(self):
        initial_party_count = Party.objects.count()
        party_data = {'name': 'New Party', 'slogan': 'A new hope'}

        url = reverse('party-list')
        response = self.client.post(url, party_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Party.objects.count(), initial_party_count + 1)
        self.assertEqual(response.data['name'], 'New Party')


class StatsViewAPITests(APITestCase):
    def test_get_stats(self):
        # Optionally create some data
        Party.objects.create(name="Stat Party")
        session = Session.objects.create(
            conf_id="stat_conf", era_co="21", sess="1", dgr="1",
            conf_dt=datetime.date.today(), conf_knd="본회의", cmit_nm="본회의",
            bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="http://example.com/stat"
        )
        speaker = Speaker.objects.create(
            naas_cd="stat_speaker", naas_nm="나의원", plpt_nm="통계당",
            elecd_nm="비례", elecd_div_nm="비례", rlct_div_nm="초선", gtelt_eraco="21", ntr_div="여"
        )
        Bill.objects.create(bill_id="stat_bill", session=session, bill_nm="통계법", link_url="http://example.com/stat_bill")
        Statement.objects.create(session=session, speaker=speaker, text="통계를 중시해야 합니다.", sentiment_score=0.5, sentiment_reason="데이터 기반")

        url = reverse('stats')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_sessions', response.data)
        self.assertIn('total_bills', response.data)
        self.assertIn('total_speakers', response.data)
        self.assertIn('total_statements', response.data)
        self.assertIn('avg_sentiment', response.data)

        self.assertGreater(response.data['total_sessions'], 0)
        self.assertGreater(response.data['total_bills'], 0)
        self.assertGreater(response.data['total_speakers'], 0)
        self.assertGreater(response.data['total_statements'], 0)
        self.assertIsNotNone(response.data['avg_sentiment'])


class SpeakerAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.login(username='testuser', password='testpassword')

        Speaker.objects.create(
            naas_cd="speaker1", naas_nm="김갑동", plpt_nm="국민의힘",
            elecd_nm="서울 강남갑", elecd_div_nm="지역구", rlct_div_nm="초선", gtelt_eraco="21", ntr_div="남"
        )
        Speaker.objects.create(
            naas_cd="speaker2", naas_nm="이을순", plpt_nm="더불어민주당",
            elecd_nm="부산 해운대을", elecd_div_nm="지역구", rlct_div_nm="재선", gtelt_eraco="20,21", ntr_div="여"
        )
        Speaker.objects.create(
            naas_cd="speaker3", naas_nm="박병철", plpt_nm="정의당",
            elecd_nm="서울 강남갑", elecd_div_nm="지역구", rlct_div_nm="3선", gtelt_eraco="19,20,21", ntr_div="남"
        )

    def test_filter_speakers_by_elecd_nm(self):
        url = reverse('speaker-list')
        response = self.client.get(url, {'elecd_nm': '서울 강남갑'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming StandardResultsSetPagination is used, results are in response.data['results']
        self.assertEqual(len(response.data['results']), 2)
        for speaker_data in response.data['results']:
            self.assertIn("서울 강남갑", speaker_data['elecd_nm'])

    def test_filter_speakers_by_elecd_nm_no_match(self):
        url = reverse('speaker-list')
        response = self.client.get(url, {'elecd_nm': '없는선거구'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_filter_speakers_by_elecd_nm_partial_match(self):
        url = reverse('speaker-list')
        response = self.client.get(url, {'elecd_nm': '강남'}) # Partial match
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        for speaker_data in response.data['results']:
            self.assertIn("강남", speaker_data['elecd_nm'])

    def test_get_statements_all(self):
        speaker = Speaker.objects.get(naas_cd="speaker1")
        session_today = Session.objects.create(conf_id="s_today", era_co="21", sess="1", dgr="1", conf_dt=timezone.now().date(), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url1")
        session_yesterday = Session.objects.create(conf_id="s_yesterday", era_co="21", sess="1", dgr="2", conf_dt=timezone.now().date() - datetime.timedelta(days=1), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url2")
        Statement.objects.create(session=session_today, speaker=speaker, text="Statement today", sentiment_score=0.0, sentiment_reason="")
        Statement.objects.create(session=session_yesterday, speaker=speaker, text="Statement yesterday", sentiment_score=0.0, sentiment_reason="")

        url = reverse('speaker-statements', kwargs={'pk': speaker.pk})
        response = self.client.get(url, {'time_range': 'all'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2) # Check paginated count

    def test_get_statements_year(self):
        speaker = Speaker.objects.get(naas_cd="speaker1")
        session_this_year = Session.objects.create(conf_id="s_this_year", era_co="21", sess="2", dgr="1", conf_dt=timezone.now().date() - datetime.timedelta(days=10), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url_ty")
        session_last_year = Session.objects.create(conf_id="s_last_year", era_co="21", sess="2", dgr="2", conf_dt=timezone.now().date() - datetime.timedelta(days=400), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url_ly")
        Statement.objects.create(session=session_this_year, speaker=speaker, text="Statement this year", sentiment_score=0.0, sentiment_reason="")
        Statement.objects.create(session=session_last_year, speaker=speaker, text="Statement last year", sentiment_score=0.0, sentiment_reason="")

        url = reverse('speaker-statements', kwargs={'pk': speaker.pk})
        response = self.client.get(url, {'time_range': 'year'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['text'], "Statement this year")

    def test_get_statements_month(self):
        speaker = Speaker.objects.get(naas_cd="speaker1")
        session_this_month = Session.objects.create(conf_id="s_this_month", era_co="21", sess="3", dgr="1", conf_dt=timezone.now().date() - datetime.timedelta(days=5), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url_tm")
        session_last_month = Session.objects.create(conf_id="s_last_month", era_co="21", sess="3", dgr="2", conf_dt=timezone.now().date() - datetime.timedelta(days=40), conf_knd="본회의", cmit_nm="본회의", bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="url_lm")
        Statement.objects.create(session=session_this_month, speaker=speaker, text="Statement this month", sentiment_score=0.0, sentiment_reason="")
        Statement.objects.create(session=session_last_month, speaker=speaker, text="Statement last month", sentiment_score=0.0, sentiment_reason="")

        url = reverse('speaker-statements', kwargs={'pk': speaker.pk})
        response = self.client.get(url, {'time_range': 'month'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['text'], "Statement this month")

    def test_get_statements_non_existent_speaker(self):
        url = reverse('speaker-statements', kwargs={'pk': 'nonexistentpk'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['message'], 'No Speaker matches the given query.') # Corrected expected message


class SessionAPITests(APITestCase): # New Test Class for Session API specific tests
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.login(username='testuser', password='testpassword')
        # Create a valid session for some tests if needed, but not for 404 test.

    def test_get_bills_for_non_existent_session(self):
        url = reverse('session-bills', kwargs={'pk': 'nonexistentsessionpk'}) # Use the correct action name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # The default Http404 message from Django is "No Session matches the given query."
        # The decorator will use str(e) which is this message.
        self.assertEqual(response.data['message'], 'No Session matches the given query.')


class SessionSerializerTests(APITestCase):
    def test_session_serializer_invalid_times(self):
        invalid_data = {
            "conf_id": "test_session_invalid",
            "era_co": "21",
            "sess": "350",
            "dgr": "1",
            "conf_dt": datetime.date.today(),
            "conf_knd": "본회의",
            "cmit_nm": "본회의",
            "bg_ptm": datetime.time(10, 0, 0),
            "ed_ptm": datetime.time(9, 0, 0), # Invalid: ed_ptm < bg_ptm
            "down_url": "http://example.com/session_invalid"
        }
        serializer = SessionSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors) # Error is a non_field_error due to validate()
        self.assertEqual(serializer.errors['non_field_errors'][0], "회의 종료 시간은 시작 시간보다 이후여야 합니다 (bg_ptm, ed_ptm).")

    def test_session_serializer_valid_times(self):
        valid_data = {
            "conf_id": "test_session_valid",
            "era_co": "21",
            "sess": "351",
            "dgr": "2",
            "conf_dt": datetime.date.today(),
            "conf_knd": "위원회",
            "cmit_nm": "기획재정위원회",
            "bg_ptm": datetime.time(9, 0, 0),
            "ed_ptm": datetime.time(10, 0, 0), # Valid: ed_ptm > bg_ptm
            "down_url": "http://example.com/session_valid"
        }
        serializer = SessionSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)


class StatementSerializerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.client.login(username='testuser', password='testpassword')

        self.session = Session.objects.create(
            conf_id="stmt_test_session", era_co="21", sess="400", dgr="1",
            conf_dt=datetime.date.today(), conf_knd="테스트회의", cmit_nm="테스트위원회",
            bg_ptm=datetime.time(10,0), ed_ptm=datetime.time(11,0), down_url="http://example.com/stmt_session"
        )
        self.speaker = Speaker.objects.create(
            naas_cd="stmt_test_speaker", naas_nm="테스트의원", plpt_nm="테스트당",
            elecd_nm="테스트선거구", elecd_div_nm="지역구", rlct_div_nm="초선", gtelt_eraco="21", ntr_div="남"
        )
        self.bill = Bill.objects.create(
            bill_id="stmt_test_bill", session=self.session, bill_nm="테스트법안", link_url="http://example.com/stmt_bill"
        )

    def test_create_statement_valid_text_field(self):
        valid_data = {
            'session': self.session.pk,
            'speaker': self.speaker.pk,
            'bill': self.bill.pk,
            'text': 'This is a valid statement text that is long enough.',
            'sentiment_score': 0.5
        }
        serializer = StatementCreateSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid(), msg=serializer.errors)
        statement = serializer.save()
        self.assertIsInstance(statement, Statement)
        self.assertEqual(Statement.objects.count(), 1)
        self.assertEqual(statement.text, valid_data['text'])

    def test_create_statement_invalid_short_text(self):
        invalid_data = {
            'session': self.session.pk,
            'speaker': self.speaker.pk,
            'bill': self.bill.pk,
            'text': 'Too short',
            'sentiment_score': 0.5
        }
        serializer = StatementCreateSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('text', serializer.errors)
        self.assertEqual(serializer.errors['text'][0], "발언 내용은 10자 이상이어야 합니다.") # Corrected expected error message

    def test_create_statement_missing_text(self):
        invalid_data = {
            'session': self.session.pk,
            'speaker': self.speaker.pk,
            'bill': self.bill.pk,
            'sentiment_score': 0.5
            # 'text' field is missing
        }
        serializer = StatementCreateSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('text', serializer.errors)
        self.assertEqual(serializer.errors['text'][0], "이 필드는 필수 항목입니다.") # Corrected expected error message
