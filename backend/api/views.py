from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework.exceptions import NotFound, PermissionDenied
from .utils import api_action_wrapper
from .models import Session, Bill, Speaker, Statement, Party, Category, Subcategory, StatementCategory, VotingRecord
from .serializers import (SessionSerializer, BillSerializer, SpeakerSerializer,
                          StatementSerializer, StatementCreateSerializer,
                          PartySerializer, CategorySerializer,
                          VotingRecordSerializer)
from .llm_analyzer import LLMPolicyAnalyzer
import logging
from django.utils import timezone
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Avg
from datetime import datetime, timedelta
from .models import Session, Bill, Speaker, Statement, Party, Category
from .serializers import (SessionSerializer, BillSerializer, SpeakerSerializer,
                          StatementSerializer, PartySerializer)
from .tasks import is_celery_available
from django.db.models import Count, Avg
from datetime import datetime, timedelta
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models
from django.db.models import F
from django.db import connection
from .utils import ensure_basic_data_exists

logger = logging.getLogger(__name__)


# Import celery availability check
def is_celery_available():
    """Check if Celery/Redis is available for async tasks"""
    from kombu.exceptions import OperationalError
    from celery import current_app
    try:
        current_app.control.inspect().active()
        return True
    except (ImportError, OperationalError, OSError, ConnectionError):
        return False


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return SessionListSerializer  # Use optimized serializer for list view
        return SessionSerializer

    def get_queryset(self):
        try:
            # Ultra-optimized queryset for listing
            if self.action == 'list':
                base_queryset = Session.objects.only(
                    'conf_id', 'era_co', 'sess', 'dgr', 'conf_dt',
                    'conf_knd', 'cmit_nm', 'title').filter(
                        era_co__in=['22', '제22대'
                                    ])  # Always filter to 22nd Assembly first
            else:
                base_queryset = Session.objects.all()

            # Apply filters only if provided
            era_co = self.request.query_params.get('era_co')
            if era_co and era_co not in ['all', '22', '제22대']:
                base_queryset = base_queryset.filter(era_co=era_co)

            sess = self.request.query_params.get('sess')
            if sess:
                base_queryset = base_queryset.filter(sess=sess)

            dgr = self.request.query_params.get('dgr')
            if dgr:
                base_queryset = base_queryset.filter(dgr=dgr)

            date_from = self.request.query_params.get('date_from')
            if date_from:
                try:
                    base_queryset = base_queryset.filter(
                        conf_dt__gte=date_from)
                except ValueError:
                    pass

            date_to = self.request.query_params.get('date_to')
            if date_to:
                try:
                    base_queryset = base_queryset.filter(conf_dt__lte=date_to)
                except ValueError:
                    pass

            return base_queryset.order_by('-conf_dt')
        except Exception as e:
            logger.error(f"Error in SessionViewSet get_queryset: {e}")
            return Session.objects.none()

    def list(self, request, *args, **kwargs):
        try:
            # Use raw query for better performance
            from django.db import connection

            era_filter = "era_co IN ('22', '제22대')"

            # Build additional filters
            additional_filters = []
            params = []

            sess = request.query_params.get('sess')
            if sess:
                additional_filters.append("sess = %s")
                params.append(sess)

            dgr = request.query_params.get('dgr')
            if dgr:
                additional_filters.append("dgr = %s")
                params.append(dgr)

            date_from = request.query_params.get('date_from')
            if date_from:
                additional_filters.append("conf_dt >= %s")
                params.append(date_from)

            date_to = request.query_params.get('date_to')
            if date_to:
                additional_filters.append("conf_dt <= %s")
                params.append(date_to)

            where_clause = era_filter
            if additional_filters:
                where_clause += " AND " + " AND ".join(additional_filters)

            # Execute optimized query
            with connection.cursor() as cursor:
                query = f"""
                SELECT conf_id, era_co, sess, dgr, conf_dt, conf_knd, cmit_nm, title
                FROM api_session 
                WHERE {where_clause}
                ORDER BY conf_dt DESC 
                LIMIT 20
                """
                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Convert to list of dicts
                results = []
                for row in rows:
                    results.append({
                        'conf_id': row[0],
                        'era_co': row[1],
                        'sess': row[2],
                        'dgr': row[3],
                        'conf_dt': row[4],
                        'conf_knd': row[5],
                        'cmit_nm': row[6],
                        'title': row[7],
                        'bills': [],  # Empty for performance
                        'statements': []  # Empty for performance
                    })

                return Response({
                    'count': len(results),
                    'next': None,
                    'previous': None,
                    'results': results
                })

        except Exception as e:
            logger.error(f"Error in SessionViewSet list: {e}")
            return Response(
                {
                    'count': 0,
                    'next': None,
                    'previous': None,
                    'results': []
                },
                status=200)

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching bills for session",
                        default_error_message='의안 목록을 불러오는 중 오류가 발생했습니다.')
    def bills(self, request, pk=None):
        session = self.get_object()
        bills = session.bills.all()
        serializer = BillSerializer(bills, many=True)
        return Response({'status': 'success', 'data': serializer.data})

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching statements for session",
                        default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        session = self.get_object()
        statements = session.statements.select_related('speaker', 'bill').all()
        serializer = StatementSerializer(statements, many=True)
        return Response(serializer.data)


class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    pagination_class = StandardResultsSetPagination

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to ensure consistent response format"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)

            # Add extra data for the bill
            response_data = serializer.data

            # Add statement count
            statement_count = Statement.objects.filter(bill=instance).count()
            response_data['statement_count'] = statement_count

            # Add voting records count if available
            try:
                voting_count = VotingRecord.objects.filter(
                    bill=instance).count()
                response_data['voting_count'] = voting_count
            except:
                response_data['voting_count'] = 0

            return Response(response_data)
        except Http404:
            return Response({'detail': 'Bill not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error retrieving bill {kwargs.get('pk')}: {e}")
            return Response({'detail': 'Failed to retrieve bill'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_queryset(self):
        # Optimize with select_related and prefetch_related
        queryset = super().get_queryset().select_related(
            'session').prefetch_related('statements')

        bill_name = self.request.query_params.get('bill_name')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if bill_name:
            queryset = queryset.filter(bill_nm__icontains=bill_name)
        if date_from:
            queryset = queryset.filter(session__conf_dt__gte=date_from)
        if date_to:
            queryset = queryset.filter(session__conf_dt__lte=date_to)

        # Order by session date (most recent first), then by creation time
        return queryset.order_by('-session__conf_dt', '-created_at')

    def list(self, request, *args, **kwargs):
        """Override list to ensure consistent response format"""
        try:
            queryset = self.filter_queryset(self.get_queryset())

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error in BillViewSet list: {e}")
            return Response([], status=200)

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching statements for bill",
                        default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        try:
            bill = self.get_object()
            logger.info(f"Fetching statements for bill: {bill.bill_id}")
            statements = bill.statements.all()
            logger.info(
                f"Found {statements.count()} statements for bill {bill.bill_id}"
            )
            serializer = StatementSerializer(statements, many=True)
            return Response({'status': 'success', 'data': serializer.data})
        except Exception as e:
            logger.error(f"Error fetching statements for bill {pk}: {e}")
            return Response({'status': 'error', 'message': str(e)}, status=500)

    @action(detail=True, methods=['get'], url_path='voting-sentiment')
    def voting_sentiment(self, request, pk=None):
        """Get comprehensive sentiment analysis for a bill including voting records"""
        try:
            bill = self.get_object()

            # Get statements for this bill
            statements = Statement.objects.filter(bill=bill)

            # Get voting records for this bill - make this optional
            voting_records = VotingRecord.objects.filter(bill=bill) if hasattr(
                VotingRecord, 'objects') else VotingRecord.objects.none()

            # Combine sentiment from statements and voting
            combined_sentiment = {}

            # Process statements
            for statement in statements:
                party_name = statement.speaker.get_current_party_name()
                speaker_name = statement.speaker.naas_nm

                if party_name not in combined_sentiment:
                    combined_sentiment[party_name] = {
                        'party_name': party_name,
                        'members': {},
                        'statement_count': 0,
                        'voting_count': 0,
                        'avg_statement_sentiment': 0,
                        'avg_voting_sentiment': 0,
                        'combined_sentiment': 0
                    }

                if speaker_name not in combined_sentiment[party_name][
                        'members']:
                    combined_sentiment[party_name]['members'][speaker_name] = {
                        'speaker_name': speaker_name,
                        'statements': [],
                        'vote_result': None,
                        'vote_sentiment': 0,
                        'avg_statement_sentiment': 0,
                        'combined_sentiment': 0
                    }

                combined_sentiment[party_name]['members'][speaker_name][
                    'statements'].append({
                        'text':
                        statement.text[:200] +
                        '...' if len(statement.text) > 200 else statement.text,
                        'sentiment_score':
                        statement.sentiment_score or 0,
                        'created_at':
                        statement.created_at
                    })

                combined_sentiment[party_name]['statement_count'] += 1

            # Process voting records if available
            for vote in voting_records:
                party_name = vote.speaker.get_current_party_name()
                speaker_name = vote.speaker.naas_nm

                if party_name not in combined_sentiment:
                    combined_sentiment[party_name] = {
                        'party_name': party_name,
                        'members': {},
                        'statement_count': 0,
                        'voting_count': 0,
                        'avg_statement_sentiment': 0,
                        'avg_voting_sentiment': 0,
                        'combined_sentiment': 0
                    }

                if speaker_name not in combined_sentiment[party_name][
                        'members']:
                    combined_sentiment[party_name]['members'][speaker_name] = {
                        'speaker_name': speaker_name,
                        'statements': [],
                        'vote_result': None,
                        'vote_sentiment': 0,
                        'avg_statement_sentiment': 0,
                        'combined_sentiment': 0
                    }

                combined_sentiment[party_name]['members'][speaker_name][
                    'vote_result'] = vote.vote_result
                combined_sentiment[party_name]['members'][speaker_name][
                    'vote_sentiment'] = vote.sentiment_score
                combined_sentiment[party_name]['voting_count'] += 1

            # Calculate averages and combined sentiment
            for party_data in combined_sentiment.values():
                statement_sentiments = []
                voting_sentiments = []

                for member_data in party_data['members'].values():
                    # Calculate average statement sentiment for member
                    if member_data['statements']:
                        member_statement_avg = sum(
                            s['sentiment_score']
                            for s in member_data['statements']) / len(
                                member_data['statements'])
                        member_data['avg_statement_sentiment'] = round(
                            member_statement_avg, 3)
                        statement_sentiments.append(member_statement_avg)

                    # Add voting sentiment
                    if member_data['vote_result']:
                        voting_sentiments.append(member_data['vote_sentiment'])

                    # Calculate combined sentiment (weighted average of statements and voting)
                    statement_weight = 0.6 if member_data['statements'] else 0
                    voting_weight = 0.4 if member_data['vote_result'] else 0

                    if statement_weight > 0 and voting_weight > 0:
                        member_data['combined_sentiment'] = round(
                            (member_data['avg_statement_sentiment'] *
                             statement_weight +
                             member_data['vote_sentiment'] * voting_weight), 3)
                    elif statement_weight > 0:
                        member_data['combined_sentiment'] = member_data[
                            'avg_statement_sentiment']
                    elif voting_weight > 0:
                        member_data['combined_sentiment'] = member_data[
                            'vote_sentiment']

                # Calculate party averages
                if statement_sentiments:
                    party_data['avg_statement_sentiment'] = round(
                        sum(statement_sentiments) / len(statement_sentiments),
                        3)
                if voting_sentiments:
                    party_data['avg_voting_sentiment'] = round(
                        sum(voting_sentiments) / len(voting_sentiments), 3)

                # Calculate combined party sentiment
                all_member_sentiments = [
                    m['combined_sentiment']
                    for m in party_data['members'].values()
                    if m['combined_sentiment'] != 0
                ]
                if all_member_sentiments:
                    party_data['combined_sentiment'] = round(
                        sum(all_member_sentiments) /
                        len(all_member_sentiments), 3)

            # Convert to list and sort by combined sentiment
            party_list = list(combined_sentiment.values())
            party_list.sort(key=lambda x: x['combined_sentiment'],
                            reverse=True)

            # Calculate overall statistics
            total_voting_records = voting_records.count()
            vote_distribution = voting_records.values('vote_result').annotate(
                count=Count('id')) if voting_records.exists() else []

            return Response({
                'bill': {
                    'id': bill.bill_id,
                    'name': bill.bill_nm,
                    'session_date':
                    bill.session.conf_dt if bill.session else None
                },
                'summary': {
                    'total_statements': statements.count(),
                    'total_voting_records': total_voting_records,
                    'vote_distribution': list(vote_distribution)
                },
                'party_analysis': party_list
            })

        except Exception as e:
            logger.error(f"Error in bill voting sentiment analysis: {e}")
            return Response(
                {'error': 'Failed to fetch bill voting sentiment analysis'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def sentiment(self, request, pk=None):
        """Get detailed sentiment analysis for a specific bill"""
        try:
            bill = self.get_object()
            statements = Statement.objects.filter(bill=bill)

            # Initialize default response structure
            response_data = {
                'bill': {
                    'id': bill.bill_id,
                    'name': bill.bill_nm
                },
                'sentiment_summary': {
                    'total_statements': 0,
                    'average_sentiment': 0,
                    'positive_count': 0,
                    'neutral_count': 0,
                    'negative_count': 0,
                    'positive_percentage': 0,
                    'negative_percentage': 0
                },
                'party_breakdown': [],
                'speaker_breakdown': [],
                'sentiment_timeline': []
            }

            if not statements.exists():
                return Response(response_data)

            # Calculate sentiment summary
            total_statements = statements.count()
            average_sentiment = statements.aggregate(
                avg=Avg('sentiment_score'))['avg'] or 0
            positive_count = statements.filter(sentiment_score__gt=0.3).count()
            negative_count = statements.filter(
                sentiment_score__lt=-0.3).count()
            neutral_count = total_statements - positive_count - negative_count

            # Party breakdown
            party_breakdown = statements.values('speaker__plpt_nm').annotate(
                count=Count('id'),
                avg_sentiment=Avg('sentiment_score'),
                positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
                negative_count=Count('id', filter=Q(
                    sentiment_score__lt=-0.3))).order_by('-avg_sentiment')

            # Top speakers by sentiment (most positive and most negative)
            speaker_breakdown = statements.values(
                'speaker__naas_nm', 'speaker__plpt_nm').annotate(
                    count=Count('id'),
                    avg_sentiment=Avg('sentiment_score')).filter(
                        count__gte=2).order_by('-avg_sentiment')[:10]

            # Sentiment timeline (by session date)
            timeline_data = statements.values('session__conf_dt').annotate(
                avg_sentiment=Avg('sentiment_score'),
                count=Count('id')).order_by('session__conf_dt')

            return Response({
                'bill': {
                    'id': bill.bill_id,
                    'name': bill.bill_nm
                },
                'sentiment_summary': {
                    'total_statements':
                    total_statements,
                    'average_sentiment':
                    round(average_sentiment, 3),
                    'positive_count':
                    positive_count,
                    'neutral_count':
                    neutral_count,
                    'negative_count':
                    negative_count,
                    'positive_percentage':
                    round((positive_count / total_statements) * 100, 1),
                    'negative_percentage':
                    round((negative_count / total_statements) * 100, 1)
                },
                'party_breakdown':
                list(party_breakdown),
                'speaker_breakdown':
                list(speaker_breakdown),
                'sentiment_timeline': [{
                    'date':
                    item['session__conf_dt'].strftime('%Y-%m-%d'),
                    'avg_sentiment':
                    round(item['avg_sentiment'], 3),
                    'statement_count':
                    item['count']
                } for item in timeline_data]
            })

        except Exception as e:
            logger.error(f"Error in bill sentiment analysis: {e}")
            return Response({'error': 'Failed to fetch sentiment analysis'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SpeakerViewSet(viewsets.ModelViewSet):
    queryset = Speaker.objects.all()
    serializer_class = SpeakerSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Filter to only show 22nd Assembly speakers
        queryset = super().get_queryset().filter(
            models.Q(gtelt_eraco__icontains='22')
            | models.Q(gtelt_eraco__icontains='제22대'))
        name = self.request.query_params.get('name')
        party = self.request.query_params.get('party')
        elecd_nm_param = self.request.query_params.get('elecd_nm')
        era_co = self.request.query_params.get('era_co')

        if name:
            queryset = queryset.filter(naas_nm__icontains=name)
        if party:
            queryset = queryset.filter(plpt_nm__icontains=party)
        if elecd_nm_param:
            queryset = queryset.filter(elecd_nm__icontains=elecd_nm_param)
        if era_co and era_co != '22':
            # Only allow 22nd assembly
            return Speaker.objects.none()

        return queryset.order_by('naas_nm')

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching statements for speaker",
                        default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        speaker = self.get_object()
        time_range = request.query_params.get('time_range', 'all')

        statements_qs = speaker.statements.all()

        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() -
                timezone.timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timezone.timedelta(days=30))

        ordered_statements = statements_qs.order_by('-session__conf_dt',
                                                    '-created_at')

        page = self.paginate_queryset(ordered_statements)
        if page is not None:
            serializer = StatementSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = StatementSerializer(ordered_statements, many=True)
        return Response({'status': 'success', 'data': serializer.data})


class StatementViewSet(viewsets.ModelViewSet):
    queryset = Statement.objects.all()
    serializer_class = StatementSerializer
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        if self.action == 'create':
            return StatementCreateSerializer
        return StatementSerializer

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(
                {
                    'status': 'success',
                    'data': StatementSerializer(serializer.instance).data
                },
                status=status.HTTP_201_CREATED,
                headers=headers)
        except ValidationError as e:
            logger.error(f"Validation error creating statement: {e}")
            return Response({
                'status': 'error',
                'message': str(e)
            },
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating statement: {e}")
            return Response(
                {
                    'status': 'error',
                    'message': '발언을 생성하는 중 오류가 발생했습니다.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PartyViewSet(viewsets.ModelViewSet):
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    filter_backends = [
        DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter
    ]
    filterset_fields = ['name']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'id']
    ordering = ['name']

    def get_queryset(self):
        try:
            queryset = Party.objects.all()
            time_range = self.request.query_params.get('time_range', 'all')
            categories = self.request.query_params.get('categories')

            return queryset
        except Exception as e:
            logger.error(f"Error in PartyViewSet get_queryset: {e}")
            return Party.objects.none()

    def list(self, request, *args, **kwargs):
        try:
            fetch_additional = request.query_params.get(
                'fetch_additional', 'false').lower() == 'true'

            if fetch_additional:
                try:
                    from .tasks import fetch_additional_data_nepjpxkkabqiqpbvk
                    if is_celery_available():
                        fetch_additional_data_nepjpxkkabqiqpbvk.delay()
                    else:
                        fetch_additional_data_nepjpxkkabqiqpbvk()
                except Exception as e:
                    logger.error(
                        f"Error triggering additional data fetch: {e}")

            # Single optimized query to get all party statistics
            from django.db.models import Case, When, IntegerField, Value

            party_stats = Party.objects.filter(assembly_era=22).annotate(
                member_count=Count(
                    'current_members',
                    filter=Q(current_members__gtelt_eraco__icontains='22'),
                    distinct=True),
                total_statements=Count(
                    'current_members__statements',
                    filter=Q(current_members__statements__session__era_co__in=[
                        '22', '제22대'
                    ]),
                    distinct=True),
                avg_sentiment=Avg(
                    'current_members__statements__sentiment_score',
                    filter=Q(current_members__statements__session__era_co__in=[
                        '22', '제22대'
                    ]))).order_by('-member_count')

            party_data = []
            for party in party_stats:
                party_info = {
                    'id':
                    party.id,
                    'name':
                    party.name,
                    'description':
                    party.description,
                    'slogan':
                    party.slogan,
                    'logo_url':
                    party.logo_url,
                    'assembly_era':
                    party.assembly_era,
                    'member_count':
                    party.member_count,
                    'total_statements':
                    party.total_statements,
                    'avg_sentiment':
                    round(party.avg_sentiment or 0, 3),
                    'approved_bills':
                    0,
                    'rejected_bills':
                    0,
                    'recent_statements': [],
                    'top_members': [],
                    'created_at':
                    party.created_at.isoformat() if party.created_at else None,
                    'updated_at':
                    party.updated_at.isoformat() if party.updated_at else None
                }

                if party.member_count > 0 or party.total_statements > 0:
                    party_data.append(party_info)

            if fetch_additional:
                return Response({
                    'results': party_data,
                    'count': len(party_data),
                    'additional_data_fetched': True
                })

            return Response(party_data)

        except Exception as e:
            logger.error(f"Error in PartyViewSet list: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response([], status=200)


class StatementListView(generics.ListAPIView):
    serializer_class = StatementSerializer

    def get_queryset(self):
        bill_id = self.kwargs.get('bill_id')
        return Statement.objects.filter(bill_id=bill_id)


@api_view(['GET'])
def statement_list(request):
    """List all statements with pagination and filtering"""
    try:
        statements_qs = Statement.objects.filter(
            session__era_co='22').select_related('speaker', 'session',
                                                 'bill').all()

        # Apply filters
        speaker_id = request.query_params.get('speaker_id')
        session_id = request.query_params.get('session_id')
        bill_id = request.query_params.get('bill_id')
        sentiment_min = request.query_params.get('sentiment_min')
        sentiment_max = request.query_params.get('sentiment_max')

        if speaker_id:
            statements_qs = statements_qs.filter(speaker_id=speaker_id)
        if session_id:
            statements_qs = statements_qs.filter(session_id=session_id)
        if bill_id:
            statements_qs = statements_qs.filter(bill_id=bill_id)
        if sentiment_min:
            statements_qs = statements_qs.filter(
                sentiment_score__gte=float(sentiment_min))
        if sentiment_max:
            statements_qs = statements_qs.filter(
                sentiment_score__lte=float(sentiment_max))

        # Pagination
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(
            statements_qs.order_by('-created_at'), request)
        serializer = StatementSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error in statement_list: {e}")
        return Response({'error': 'Failed to fetch statements'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def bill_list(request):
    """List all bills with pagination and filtering"""
    try:
        bills_qs = Bill.objects.filter(
            session__era_co='22').select_related('session').all()

        # Apply filters
        session_id = request.query_params.get('session_id')
        bill_name = request.query_params.get('name')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if session_id:
            bills_qs = bills_qs.filter(session_id=session_id)
        if bill_name:
            bills_qs = bills_qs.filter(bill_nm__icontains=bill_name)
        if date_from:
            bills_qs = bills_qs.filter(session__conf_dt__gte=date_from)
        if date_to:
            bills_qs = bills_qs.filter(session__conf_dt__lte=date_to)

        # Pagination - order by session date first, then creation time
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(
            bills_qs.order_by('-session__conf_dt', '-created_at'), request)
        serializer = BillSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error in bill_list: {e}")
        return Response({'error': 'Failed to fetch bills'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def refresh_all_data(request):
    """Trigger complete data refresh from APIs"""
    try:
        from .tasks import fetch_continuous_sessions

        # Start data collection
        force = request.data.get('force', False)
        debug = request.data.get('debug', False)

        if is_celery_available():
            task = fetch_continuous_sessions.delay(force=force, debug=debug)
            return Response({
                'message': 'Data refresh started',
                'task_id': task.id,
                'status': 'started'
            })
        else:
            # Run synchronously if Celery not available
            fetch_continuous_sessions(force=force, debug=debug)
            return Response({
                'message': 'Data refresh completed',
                'status': 'completed'
            })

    except Exception as e:
        logger.error(f"Error triggering data refresh: {e}")
        return Response({'error': 'Failed to start data refresh'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def data_status(request):
    """Real-time data collection status monitoring endpoint"""

    # Basic counts
    session_count = Session.objects.count()
    bill_count = Bill.objects.count()
    speaker_count = Speaker.objects.count()
    statement_count = Statement.objects.count()

    # Recent activity (last 24 hours)
    yesterday = datetime.now() - timedelta(hours=24)
    recent_sessions = Session.objects.filter(created_at__gte=yesterday).count()
    recent_bills = Bill.objects.filter(created_at__gte=yesterday).count()
    recent_statements = Statement.objects.filter(
        created_at__gte=yesterday).count()

    # Processing status
    sessions_with_statements = Session.objects.annotate(
        statement_count=Count('statements')).filter(
            statement_count__gt=0).count()

    sessions_with_pdfs = Session.objects.exclude(down_url='').count()

    processing_rate = 0
    if session_count > 0:
        processing_rate = (sessions_with_statements / session_count) * 100

    # Sentiment analysis
    sentiment_data = {}
    if statement_count > 0:
        avg_sentiment = Statement.objects.aggregate(
            avg_sentiment=Avg('sentiment_score'))['avg_sentiment']

        positive_statements = Statement.objects.filter(
            sentiment_score__gt=0.3).count()
        negative_statements = Statement.objects.filter(
            sentiment_score__lt=-0.3).count()
        neutral_statements = statement_count - positive_statements - negative_statements

        sentiment_data = {
            'average_sentiment':
            round(avg_sentiment, 3) if avg_sentiment else 0,
            'positive_count': positive_statements,
            'neutral_count': neutral_statements,
            'negative_count': negative_statements
        }

    # Latest data
    latest_session = Session.objects.order_by('-created_at').first()
    latest_statement = Statement.objects.order_by('-created_at').first()

    return Response({
        'total_counts': {
            'sessions': session_count,
            'bills': bill_count,
            'speakers': speaker_count,
            'statements': statement_count
        },
        'recent_activity': {
            'new_sessions_24h': recent_sessions,
            'new_bills_24h': recent_bills,
            'new_statements_24h': recent_statements
        },
        'processing_status': {
            'sessions_with_pdfs': sessions_with_pdfs,
            'sessions_with_statements': sessions_with_statements,
            'processing_completion_rate': round(processing_rate, 1)
        },
        'sentiment_analysis': sentiment_data,
        'latest_data': {
            'latest_session': {
                'id': latest_session.conf_id if latest_session else None,
                'created_at':
                latest_session.created_at if latest_session else None
            },
            'latest_statement': {
                'created_at':
                latest_statement.created_at if latest_statement else None,
                'speaker':
                latest_statement.speaker.naas_nm if latest_statement else None,
                'sentiment':
                round(latest_statement.sentiment_score, 2) if latest_statement
                and latest_statement.sentiment_score else None
            }
        },
        'last_updated': datetime.now()
    })


class CategoryListView(generics.ListAPIView):
    """List all categories with their subcategories"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


@api_view(['GET'])
def category_analytics(request):
    """Get category-based analytics for sentiment and activity"""
    try:
        time_range = request.query_params.get('time_range', 'all')
        categories_param = request.query_params.get('categories')

        statements_qs = Statement.objects.all()

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))

        # Apply category filter if provided
        if categories_param:
            category_ids = [
                int(id.strip()) for id in categories_param.split(',')
                if id.strip()
            ]
            statements_qs = statements_qs.filter(
                categories__category_id__in=category_ids)

        # Get category analytics
        category_data = []
        for category in Category.objects.all():
            category_statements = statements_qs.filter(
                categories__category=category).distinct()

            if category_statements.exists():
                avg_sentiment = category_statements.aggregate(
                    avg_sentiment=Avg('sentiment_score'))['avg_sentiment'] or 0

                statement_count = category_statements.count()

                # Get party breakdown for this category
                party_breakdown = category_statements.values(
                    'speaker__plpt_nm').annotate(
                        count=Count('id'),
                        avg_sentiment=Avg('sentiment_score')).order_by(
                            '-count')[:5]

                category_data.append({
                    'category_id': category.id,
                    'category_name': category.name,
                    'statement_count': statement_count,
                    'avg_sentiment': round(avg_sentiment, 3),
                    'party_breakdown': list(party_breakdown)
                })

        return Response({
            'results': category_data,
            'total_categories': len(category_data),
            'time_range': time_range
        })

    except Exception as e:
        logger.error(f"Error in category analytics: {e}")
        return Response({'error': 'Failed to fetch category analytics'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.views.decorators.http import require_POST
from django.core.management import call_command
from django.http import JsonResponse
import io
import sys


@require_POST
def trigger_force_collection(request):
    """Trigger force collection via API"""
    try:
        # Capture output
        out = io.StringIO()
        call_command('force_collection', stdout=out)
        return JsonResponse({'status': 'success', 'output': out.getvalue()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)


def check_data_status(request):
    """Check data status via API"""
    try:
        out = io.StringIO()
        call_command('check_data_status', stdout=out)
        return JsonResponse({'status': 'success', 'output': out.getvalue()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

        statements_qs = Statement.objects.all()

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))

        # Apply category filter if provided
        if categories_param:
            category_ids = [
                int(id.strip()) for id in categories_param.split(',')
                if id.strip()
            ]
            statements_qs = statements_qs.filter(
                categories__category_id__in=category_ids)

        # Get category analytics
        category_data = []
        for category in Category.objects.all():
            category_statements = statements_qs.filter(
                categories__category=category).distinct()

            if category_statements.exists():
                avg_sentiment = category_statements.aggregate(
                    avg_sentiment=Avg('sentiment_score'))['avg_sentiment'] or 0

                statement_count = category_statements.count()

                # Get party breakdown for this category
                party_breakdown = category_statements.values(
                    'speaker__plpt_nm').annotate(
                        count=Count('id'),
                        avg_sentiment=Avg('sentiment_score')).order_by(
                            '-count')[:5]

                category_data.append({
                    'category_id': category.id,
                    'category_name': category.name,
                    'statement_count': statement_count,
                    'avg_sentiment': round(avg_sentiment, 3),
                    'party_breakdown': list(party_breakdown)
                })

        return Response({
            'results': category_data,
            'total_categories': len(category_data),
            'time_range': time_range
        })

    except Exception as e:
        logger.error(f"Error in category analytics: {e}")
        return Response({'error': 'Failed to fetch category analytics'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def category_trend_analysis(request, category_id):
    """Get trend analysis for a specific category over time"""
    try:
        category = get_object_or_404(Category, id=category_id)

        # Get statements for this category over the last year
        one_year_ago = timezone.now().date() - timedelta(days=365)
        statements = Statement.objects.filter(
            categories__category=category,
            session__conf_dt__gte=one_year_ago).order_by('session__conf_dt')

        # Group by month
        monthly_data = {}
        for statement in statements:
            month_key = statement.session.conf_dt.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = {'count': 0, 'sentiment_scores': []}
            monthly_data[month_key]['count'] += 1
            if statement.sentiment_score is not None:
                monthly_data[month_key]['sentiment_scores'].append(
                    statement.sentiment_score)

        # Calculate monthly averages
        trend_data = []
        for month, data in sorted(monthly_data.items()):
            if data['sentiment_scores']:
                avg_sentiment = sum(data['sentiment_scores']) / len(
                    data['sentiment_scores'])
            else:
                avg_sentiment = 0
            trend_data.append({
                'month': month,
                'statement_count': data['count'],
                'avg_sentiment': round(avg_sentiment, 3)
            })

        return Response({
            'category': {
                'id': category.id,
                'name': category.name
            },
            'trend_data': trend_data
        })

    except Exception as e:
        logger.error(f"Error in category trend analysis: {e}")
        return Response({'error': 'Failed to fetch category trends'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def overall_sentiment_stats(request):
    """Get overall sentiment statistics across all statements"""
    try:
        time_range = request.query_params.get('time_range', 'all')

        statements_qs = Statement.objects.filter(
            session__era_co__in=['22', '제22대'])

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))
        elif time_range == 'week':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=7))

        # Get total statements count
        total_statements = statements_qs.count()

        if total_statements == 0:
            return Response({
                'time_range':
                time_range,
                'overall_stats': {
                    'total_statements': 0,
                    'average_sentiment': 0,
                    'positive_count': 0,
                    'neutral_count': 0,
                    'negative_count': 0,
                    'positive_percentage': 0,
                    'negative_percentage': 0
                },
                'party_rankings': [],
                'active_speakers': [],
                'message':
                'No statements found for the specified time range'
            })

        # Overall statistics
        avg_sentiment = statements_qs.aggregate(
            avg=Avg('sentiment_score'))['avg'] or 0

        # Sentiment distribution
        positive_count = statements_qs.filter(sentiment_score__gt=0.3).count()
        negative_count = statements_qs.filter(sentiment_score__lt=-0.3).count()
        neutral_count = total_statements - positive_count - negative_count

        # Party sentiment ranking - filter out invalid party names
        party_stats = statements_qs.exclude(
            speaker__plpt_nm__in=['', ' ', '정보없음', '무소속']
        ).values('speaker__plpt_nm').annotate(
            avg_sentiment=Avg('sentiment_score'),
            statement_count=Count('id'),
            positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
            negative_count=Count(
                'id', filter=Q(sentiment_score__lt=-0.3))).filter(
                    statement_count__gte=1).order_by('-avg_sentiment')[:10]

        # Most active speakers
        speaker_stats = statements_qs.exclude(
            speaker__naas_nm__in=['', ' ', '정보없음']).values(
                'speaker__naas_nm', 'speaker__plpt_nm').annotate(
                    avg_sentiment=Avg('sentiment_score'),
                    statement_count=Count('id')).filter(
                        statement_count__gte=1).order_by(
                            '-statement_count')[:20]

        return Response({
            'time_range': time_range,
            'overall_stats': {
                'total_statements':
                total_statements,
                'average_sentiment':
                round(avg_sentiment, 3),
                'positive_count':
                positive_count,
                'neutral_count':
                neutral_count,
                'negative_count':
                negative_count,
                'positive_percentage':
                round((positive_count / total_statements) *
                      100, 1) if total_statements > 0 else 0,
                'negative_percentage':
                round((negative_count / total_statements) *
                      100, 1) if total_statements > 0 else 0
            },
            'party_rankings': list(party_stats),
            'active_speakers': list(speaker_stats)
        })

    except Exception as e:
        logger.error(f"Error in overall sentiment stats: {e}")
        return Response(
            {
                'time_range': time_range,
                'overall_stats': {
                    'total_statements': 0,
                    'average_sentiment': 0,
                    'positive_count': 0,
                    'neutral_count': 0,
                    'negative_count': 0,
                    'positive_percentage': 0,
                    'negative_percentage': 0
                },
                'party_rankings': [],
                'active_speakers': [],
                'error': 'Failed to fetch sentiment statistics'
            },
            status=status.HTTP_200_OK)


@api_view(['GET'])
def sentiment_by_party_and_topic(request):
    """Get sentiment analysis grouped by party and topic/bill"""
    try:
        group_by = request.query_params.get('group_by',
                                            'bill')  # 'bill' or 'topic'
        time_range = request.query_params.get('time_range', 'all')

        # Base queryset for statements
        statements_qs = Statement.objects.select_related(
            'speaker', 'bill', 'session').all()

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))

        results = []

        if group_by == 'bill':
            # Group by party and bill
            party_bill_data = {}

            for statement in statements_qs.filter(
                    sentiment_score__isnull=False, bill__isnull=False):
                party_name = statement.speaker.get_current_party_name()
                bill_name = statement.bill.bill_nm

                key = f"{party_name}|{bill_name}"
                if key not in party_bill_data:
                    party_bill_data[key] = {
                        'party_name': party_name,
                        'bill_name': bill_name,
                        'bill_id': statement.bill.bill_id,
                        'sentiment_scores': [],
                        'statement_count': 0
                    }

                party_bill_data[key]['sentiment_scores'].append(
                    statement.sentiment_score)
                party_bill_data[key]['statement_count'] += 1

            # Calculate averages
            for data in party_bill_data.values():
                if data['sentiment_scores']:
                    data['avg_sentiment'] = round(
                        sum(data['sentiment_scores']) /
                        len(data['sentiment_scores']), 3)
                    data['positive_count'] = len(
                        [s for s in data['sentiment_scores'] if s > 0.3])
                    data['negative_count'] = len(
                        [s for s in data['sentiment_scores'] if s < -0.3])
                    data['neutral_count'] = data['statement_count'] - data[
                        'positive_count'] - data['negative_count']
                    # Remove raw sentiment scores to reduce response size
                    del data['sentiment_scores']
                    results.append(data)

        # Sort by average sentiment
        results.sort(key=lambda x: x['avg_sentiment'], reverse=True)

        return Response({
            'time_range': time_range,
            'category_filter': category_filter,
            'party_filter': party_filter,
            'stance_filter': stance_filter,
            'results': results,
            'total_categories_analyzed': len(results)
        })

    except Exception as e:
        logger.error(f"Error in policy_sentiment_by_category: {e}")
        return Response({'error': 'Failed to analyze policy sentiment'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def policy_sentiment_by_category(request):
    """Get sentiment analysis by policy category with stance analysis"""
    try:
        from .models import Category, Subcategory, BillCategoryMapping, BillSubcategoryMapping

        category_filter = request.query_params.get('category')
        party_filter = request.query_params.get('party')
        time_range = request.query_params.get('time_range', 'all')
        stance_filter = request.query_params.get(
            'stance')  # progressive, conservative, moderate

        # Base queryset for statements with policy analysis
        statements_qs = Statement.objects.filter(
            sentiment_score__isnull=False,
            bill__isnull=False).select_related('speaker', 'bill', 'session')

        # Apply time filter
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=timezone.now().date() -
                timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=timezone.now().date() -
                timedelta(days=30))

        # Apply party filter
        if party_filter:
            statements_qs = statements_qs.filter(
                speaker__current_party__name__icontains=party_filter)

        results = []

        # Get all categories with their policy stance data
        for category in Category.objects.all():
            if category_filter and category.name != category_filter:
                continue

            # Get bills in this category
            category_bills = Bill.objects.filter(
                category_mappings__category=category,
                category_mappings__is_primary=True)

            # Get statements for these bills
            category_statements = statements_qs.filter(bill__in=category_bills)

            if not category_statements.exists():
                continue

            # Analyze by subcategory and stance
            subcategory_analysis = []
            for subcat in category.subcategories.all():
                subcat_bills = Bill.objects.filter(
                    subcategory_mappings__subcategory=subcat,
                    subcategory_mappings__relevance_score__gte=0.5)

                subcat_statements = category_statements.filter(
                    bill__in=subcat_bills)

                if subcat_statements.exists():
                    # Get policy stance from subcategory mappings
                    stance_data = BillSubcategoryMapping.objects.filter(
                        subcategory=subcat, bill__in=subcat_bills
                    ).values('policy_position').annotate(
                        count=Count('id'),
                        avg_sentiment=Avg('bill__statements__sentiment_score'))

                    # Calculate sentiment by stance
                    stance_sentiment = {}
                    for stance_item in stance_data:
                        position = stance_item['policy_position']
                        if position and stance_item['avg_sentiment']:
                            stance_sentiment[position] = {
                                'count':
                                stance_item['count'],
                                'avg_sentiment':
                                round(stance_item['avg_sentiment'], 3)
                            }

                    subcategory_analysis.append({
                        'subcategory_name':
                        subcat.name,
                        'subcategory_description':
                        subcat.description,
                        'statement_count':
                        subcat_statements.count(),
                        'avg_sentiment':
                        round(
                            subcat_statements.aggregate(
                                avg=Avg('sentiment_score'))['avg'] or 0, 3),
                        'stance_breakdown':
                        stance_sentiment,
                        'policy_stance':
                        subcat.policy_stance if hasattr(
                            subcat, 'policy_stance') else 'moderate'
                    })

            # Party breakdown for this category
            party_breakdown = []
            party_data = category_statements.values(
                'speaker__current_party__name').annotate(
                    party_name=F('speaker__current_party__name'),
                    statement_count=Count('id'),
                    avg_sentiment=Avg('sentiment_score'),
                    positive_count=Count('id',
                                         filter=Q(sentiment_score__gt=0.3)),
                    negative_count=Count(
                        'id', filter=Q(sentiment_score__lt=-0.3))).filter(
                            statement_count__gte=3)

            for party in party_data:
                if party['party_name']:
                    party_breakdown.append({
                        'party_name':
                        party['party_name'],
                        'statement_count':
                        party['statement_count'],
                        'avg_sentiment':
                        round(party['avg_sentiment'] or 0, 3),
                        'positive_count':
                        party['positive_count'],
                        'negative_count':
                        party['negative_count'],
                        'sentiment_trend':
                        'positive'
                        if party['avg_sentiment'] > 0.1 else 'negative'
                        if party['avg_sentiment'] < -0.1 else 'neutral'
                    })

            results.append({
                'category_id':
                category.id,
                'category_name':
                category.name,
                'category_description':
                category.description,
                'total_statements':
                category_statements.count(),
                'avg_sentiment':
                round(
                    category_statements.aggregate(
                        avg=Avg('sentiment_score'))['avg'] or 0, 3),
                'subcategory_analysis':
                subcategory_analysis,
                'party_breakdown':
                sorted(party_breakdown,
                       key=lambda x: x['avg_sentiment'],
                       reverse=True),
                'policy_areas':
                len(subcategory_analysis)
            })

        # Sort by average sentiment
        results.sort(key=lambda x: x['avg_sentiment'], reverse=True)

        return Response({
            'time_range': time_range,
            'category_filter': category_filter,
            'party_filter': party_filter,
            'stance_filter': stance_filter,
            'results': results,
            'total_categories_analyzed': len(results)
        })

    except Exception as e:
        logger.error(f"Error in policy_sentiment_by_category: {e}")
        return Response({'error': 'Failed to analyze policy sentiment'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def speaker_policy_stance_analysis(request, speaker_id):
    """Analyze individual speaker's policy stances across categories"""
    try:
        speaker = get_object_or_404(Speaker, naas_cd=speaker_id)

        # Get all statements by this speaker with policy analysis
        statements = Statement.objects.filter(
            speaker=speaker, sentiment_score__isnull=False,
            bill__isnull=False).select_related('bill', 'session')

        if not statements.exists():
            return Response({
                'speaker': {
                    'id': speaker.naas_cd,
                    'name': speaker.naas_nm,
                    'party': speaker.get_current_party_name()
                },
                'policy_analysis': [],
                'overall_stance': 'insufficient_data'
            })

        # Analyze by policy category
        policy_analysis = []

        for category in Category.objects.all():
            # Get bills in this category that the speaker spoke about
            category_bills = Bill.objects.filter(
                category_mappings__category=category,
                statements__speaker=speaker).distinct()

            if not category_bills.exists():
                continue

            category_statements = statements.filter(bill__in=category_bills)

            # Analyze subcategory stances
            subcategory_stances = []
            for subcat in category.subcategories.all():
                subcat_bills = category_bills.filter(
                    subcategory_mappings__subcategory=subcat)

                if subcat_bills.exists():
                    subcat_statements = category_statements.filter(
                        bill__in=subcat_bills)

                    if subcat_statements.exists():
                        avg_sentiment = subcat_statements.aggregate(
                            avg=Avg('sentiment_score'))['avg']

                        # Determine stance based on sentiment and policy position
                        bill_positions = BillSubcategoryMapping.objects.filter(
                            subcategory=subcat,
                            bill__in=subcat_bills).values_list(
                                'policy_position', flat=True)

                        dominant_position = None
                        if bill_positions:
                            position_counts = {}
                            for pos in bill_positions:
                                if pos:
                                    position_counts[pos] = position_counts.get(
                                        pos, 0) + 1
                            if position_counts:
                                dominant_position = max(
                                    position_counts.items(),
                                    key=lambda x: x[1])[0]

                        subcategory_stances.append({
                            'subcategory':
                            subcat.name,
                            'statement_count':
                            subcat_statements.count(),
                            'avg_sentiment':
                            round(avg_sentiment, 3),
                            'policy_position':
                            dominant_position,
                            'stance_interpretation':
                            'supportive' if avg_sentiment > 0.2 else
                            'opposing' if avg_sentiment < -0.2 else 'neutral'
                        })

            if subcategory_stances:
                category_avg = category_statements.aggregate(
                    avg=Avg('sentiment_score'))['avg']

                policy_analysis.append({
                    'category':
                    category.name,
                    'category_description':
                    category.description,
                    'statement_count':
                    category_statements.count(),
                    'avg_sentiment':
                    round(category_avg, 3),
                    'subcategory_breakdown':
                    subcategory_stances,
                    'overall_stance':
                    'progressive' if category_avg > 0.3 else
                    'conservative' if category_avg < -0.3 else 'moderate'
                })

        # Calculate overall political stance
        if policy_analysis:
            overall_sentiment = sum(
                p['avg_sentiment']
                for p in policy_analysis) / len(policy_analysis)
            overall_stance = 'progressive' if overall_sentiment > 0.2 else 'conservative' if overall_sentiment < -0.2 else 'moderate'
        else:
            overall_stance = 'insufficient_data'

        return Response({
            'speaker': {
                'id': speaker.naas_cd,
                'name': speaker.naas_nm,
                'party': speaker.get_current_party_name(),
                'electoral_district': speaker.elecd_nm
            },
            'policy_analysis':
            sorted(policy_analysis,
                   key=lambda x: x['avg_sentiment'],
                   reverse=True),
            'overall_stance':
            overall_stance,
            'total_statements_analyzed':
            statements.count(),
            'active_policy_areas':
            len(policy_analysis)
        })

    except Exception as e:
        logger.error(f"Error in speaker_policy_stance_analysis: {e}")
        return Response({'error': 'Failed to analyze speaker policy stance'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def party_policy_comparison(request):
    """Compare parties' stances across policy categories"""
    try:
        from .models import Party

        category_filter = request.query_params.get('category')
        include_subcategories = request.query_params.get(
            'subcategories', 'true').lower() == 'true'

        parties = Party.objects.filter(
            current_members__isnull=False).distinct()

        comparison_data = []

        for party in parties:
            party_statements = Statement.objects.filter(
                speaker__current_party=party,
                sentiment_score__isnull=False,
                bill__isnull=False).select_related('bill')

            if not party_statements.exists():
                continue

            party_analysis = {
                'party_id': party.id,
                'party_name': party.name,
                'total_statements': party_statements.count(),
                'categories': []
            }

            for category in Category.objects.all():
                if category_filter and category.name != category_filter:
                    continue

                # Get party statements in this category
                category_bills = Bill.objects.filter(
                    category_mappings__category=category,
                    category_mappings__is_primary=True)

                category_statements = party_statements.filter(
                    bill__in=category_bills)

                if category_statements.exists():
                    category_data = {
                        'category_name':
                        category.name,
                        'statement_count':
                        category_statements.count(),
                        'avg_sentiment':
                        round(
                            category_statements.aggregate(
                                avg=Avg('sentiment_score'))['avg'], 3),
                        'stance':
                        'progressive' if category_statements.aggregate(
                            avg=Avg('sentiment_score'))['avg'] > 0.2 else
                        'conservative' if category_statements.aggregate(
                            avg=Avg('sentiment_score'))['avg'] < -0.2 else
                        'moderate'
                    }

                    if include_subcategories:
                        subcategories = []
                        for subcat in category.subcategories.all():
                            subcat_bills = category_bills.filter(
                                subcategory_mappings__subcategory=subcat)
                            subcat_statements = category_statements.filter(
                                bill__in=subcat_bills)

                            if subcat_statements.exists():
                                subcategories.append({
                                    'name':
                                    subcat.name,
                                    'statement_count':
                                    subcat_statements.count(),
                                    'avg_sentiment':
                                    round(
                                        subcat_statements.aggregate(
                                            avg=Avg('sentiment_score'))['avg'],
                                        3)
                                })

                        category_data['subcategories'] = subcategories

                    party_analysis['categories'].append(category_data)

            if party_analysis['categories']:
                # Calculate overall party stance
                overall_sentiment = sum(
                    c['avg_sentiment']
                    for c in party_analysis['categories']) / len(
                        party_analysis['categories'])
                party_analysis[
                    'overall_stance'] = 'progressive' if overall_sentiment > 0.2 else 'conservative' if overall_sentiment < -0.2 else 'moderate'
                party_analysis['overall_sentiment'] = round(
                    overall_sentiment, 3)

                comparison_data.append(party_analysis)

        # Sort by overall sentiment
        comparison_data.sort(key=lambda x: x.get('overall_sentiment', 0),
                             reverse=True)

        return Response({
            'category_filter': category_filter,
            'include_subcategories': include_subcategories,
            'party_comparison': comparison_data,
            'total_parties_analyzed': len(comparison_data)
        })

    except Exception as e:
        logger.error(f"Error in party_policy_comparison: {e}")
        return Response({'error': 'Failed to compare party policies'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def category_sentiment_analysis(request):
    """Get sentiment analysis by categories and subcategories"""
    try:
        time_range = request.query_params.get('time_range', 'all')
        party_filter = request.query_params.get('party')
        category_filter = request.query_params.get('category')

        # Base queryset for statements with categories
        statements_qs = Statement.objects.filter(
            categories__isnull=False).distinct()

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))

        # Apply party filter
        if party_filter:
            statements_qs = statements_qs.filter(
                speaker__plpt_nm__icontains=party_filter)

        # Apply category filter
        if category_filter:
            statements_qs = statements_qs.filter(
                categories__category__name=category_filter)

        # Get category-wise sentiment analysis
        category_data = []
        for category in Category.objects.all():
            category_statements = statements_qs.filter(
                categories__category=category)

            if not category_statements.exists():
                continue

            avg_sentiment = category_statements.aggregate(
                avg_sentiment=Avg('sentiment_score'))['avg_sentiment'] or 0

            statement_count = category_statements.count()
            positive_statements = category_statements.filter(
                sentiment_score__gt=0.3).count()
            negative_statements = category_statements.filter(
                sentiment_score__lt=-0.3).count()
            neutral_count = statement_count - positive_statements - negative_statements

            # Get party breakdown for this category
            party_breakdown = category_statements.values(
                'speaker__plpt_nm').annotate(
                    count=Count('id'), avg_sentiment=Avg(
                        'sentiment_score')).order_by('-avg_sentiment')[:10]

            # Get subcategory breakdown
            subcategory_breakdown = []
            for subcategory in category.subcategories.all():
                subcat_statements = category_statements.filter(
                    categories__subcategory=subcategory)
                if subcat_statements.exists():
                    subcategory_breakdown.append({
                        'subcategory_id':
                        subcategory.id,
                        'subcategory_name':
                        subcategory.name,
                        'statement_count':
                        subcat_statements.count(),
                        'avg_sentiment':
                        round(
                            subcat_statements.aggregate(
                                avg=Avg('sentiment_score'))['avg'] or 0, 3)
                    })

            category_data.append({
                'category_id':
                category.id,
                'category_name':
                category.name,
                'statement_count':
                statement_count,
                'avg_sentiment':
                round(avg_sentiment, 3),
                'positive_count':
                positive_count,
                'negative_count':
                negative_count,
                'neutral_count':
                neutral_count,
                'positive_percentage':
                round((positive_count / statement_count) * 100, 1),
                'negative_percentage':
                round((negative_count / statement_count) * 100, 1),
                'party_breakdown':
                list(party_breakdown),
                'subcategory_breakdown':
                subcategory_breakdown
            })

        # Sort by average sentiment (descending)
        category_data.sort(key=lambda x: x['avg_sentiment'], reverse=True)

        return Response({
            'time_range': time_range,
            'party_filter': party_filter,
            'category_filter': category_filter,
            'results': category_data,
            'total_categories': len(category_data)
        })

    except Exception as e:
        logger.error(f"Error in category sentiment analysis: {e}")
        return Response(
            {'error': 'Failed to fetch category sentiment analysis'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def trigger_statement_analysis(request):
    """Manually trigger LLM analysis for statements"""
    try:
        # Get statements that need analysis (no categories assigned)
        statements_to_analyze = Statement.objects.filter(
            categories__isnull=True)[:10]  # Limit to 10 for performance

        if not statements_to_analyze:
            return Response({
                'message': 'No statements need analysis',
                'analyzed_count': 0
            })

        # Import the task function locally to avoid conflicts
        from .tasks import analyze_statement_categories

        analyzed_count = 0
        for statement in statements_to_analyze:
            try:
                # Trigger async analysis
                if is_celery_available():
                    analyze_statement_categories.delay(statement.id)
                else:
                    # Run synchronously if Celery not available
                    analyze_statement_categories(statement.id)
                analyzed_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to trigger analysis for statement {statement.id}: {e}"
                )

        return Response({
            'message': f'Triggered analysis for {analyzed_count} statements',
            'analyzed_count': analyzed_count
        })

    except Exception as e:
        logger.error(f"Error triggering statement analysis: {e}")
        return Response({'error': 'Failed to trigger analysis'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def parties_list(request):
    """Get list of all parties with basic statistics and trigger additional data fetch"""
    try:
        # Ensure basic data exists before processing
        data_fetched = ensure_basic_data_exists()
        if data_fetched:
            logger.info("Basic data was fetched during party list request")

        # Check if we should fetch additional data
        fetch_additional = request.GET.get('fetch_additional',
                                           'false').lower() == 'true'

        if fetch_additional:
            # Trigger additional data collection
            try:
                from .tasks import fetch_additional_data_nepjpxkkabqiqpbvk
                if is_celery_available():
                    fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=False,
                                                                  debug=False)
                else:
                    # Run synchronously if Celery is not available
                    fetch_additional_data_nepjpxkkabqiqpbvk(force=False,
                                                            debug=False)
            except Exception as e:
                # Log but don't fail the request
                print(f"Warning: Could not trigger additional data fetch: {e}")

        parties = Party.objects.all()

        # Get basic party statistics organized by assembly era
        party_data_by_era = {}

        for party in parties:
            # Get speakers for this party
            all_speakers = Speaker.objects.filter(
                plpt_nm__icontains=party.name)
            member_count = all_speakers.count()

            # Skip if no members found
            if member_count == 0:
                continue

            # Get statements and sentiment analysis
            statements = Statement.objects.filter(
                speaker__plpt_nm__icontains=party.name)
            avg_sentiment = statements.aggregate(
                Avg('sentiment_score'))['sentiment_score__avg']
            total_statements = statements.count()

            # Get bills related to this party's speakers
            bills = Bill.objects.filter(
                statements__speaker__plpt_nm__icontains=party.name).distinct()
            total_bills = bills.count()

            party_info = {
                'id': party.id,
                'name': party.name,
                'logo_url': None,  # Don't send logo URLs to reduce requests
                'slogan': party.slogan,
                'description': party.description,
                'member_count': member_count,
                'avg_sentiment': avg_sentiment,
                'total_statements': total_statements,
                'total_bills': total_bills,
                'created_at': party.created_at,
                'updated_at': party.updated_at,
                'assembly_era': party.assembly_era
            }

            # Group by assembly era
            if party.assembly_era not in party_data_by_era:
                party_data_by_era[party.assembly_era] = []
            party_data_by_era[party.assembly_era].append(party_info)

        # Sort parties: first by assembly era (descending: 22, 21, 20...), then by name within each era
        party_data = []
        for era in sorted(party_data_by_era.keys(), reverse=True):
            era_parties = party_data_by_era[era]
            # Sort by member count (descending) within each era
            era_parties.sort(key=lambda x: (-x['member_count'], x['name']))
            party_data.extend(era_parties)

        return Response({
            'status': 'success',
            'count': len(party_data),
            'results': party_data,
            'additional_data_fetched': fetch_additional
        })

    except Exception as e:
        return Response(
            {
                'status': 'error',
                'message': f'정당 목록을 불러오는 중 오류가 발생했습니다: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def party_detail(request, party_id):
    """Get detailed information about a specific party and trigger additional data fetch"""
    try:
        party = get_object_or_404(Party, id=party_id)

        # Check if we should fetch additional data
        fetch_additional = request.GET.get('fetch_additional',
                                           'false').lower() == 'true'

        if fetch_additional:
            # Trigger additional data collection
            try:
                from .tasks import fetch_additional_data_nepjpxkkabqiqpbvk
                if is_celery_available():
                    fetch_additional_data_nepjpxkkabqiqpbvk.delay(force=False,
                                                                  debug=False)
                else:
                    # Run synchronously if Celery is not available
                    fetch_additional_data_nepjpxkkabqiqpbvk(force=False,
                                                            debug=False)
            except Exception as e:
                # Log but don't fail the request
                print(f"Warning: Could not trigger additional data fetch: {e}")

        # Get query parameters for filtering
        time_range = request.GET.get('time_range',
                                     'all')  # 'all', 'month', 'year'
        sort_by = request.GET.get(
            'sort_by', 'sentiment')  # 'sentiment', 'statements', 'bills'

        # Filter statements based on time range
        statements_filter = Q(speaker__plpt_nm=party.name)
        if time_range == 'month':
            from datetime import datetime, timedelta
            last_month = datetime.now() - timedelta(days=30)
            statements_filter &= Q(created_at__gte=last_month)
        elif time_range == 'year':
            from datetime import datetime, timedelta
            last_year = datetime.now() - timedelta(days=365)
            statements_filter &= Q(created_at__gte=last_year)

        # Get party statistics
        speakers = Speaker.objects.filter(plpt_nm=party.name)
        statements = Statement.objects.filter(statements_filter)

        # Calculate sentiment statistics
        avg_sentiment = statements.aggregate(
            Avg('sentiment_score'))['sentiment_score__avg']
        positive_statements = statements.filter(
            sentiment_score__gt=0.1).count()
        negative_statements = statements.filter(
            sentiment_score__lt=-0.1).count()
        neutral_statements = statements.filter(
            sentiment_score__gte=-0.1, sentiment_score__lte=0.1).count()

        # Get bills related to this party
        bills = Bill.objects.filter(
            statements__speaker__plpt_nm=party.name).distinct()

        # Get recent statements
        recent_statements = statements.order_by('-created_at')[:10]
        recent_statements_data = []
        for stmt in recent_statements:
            recent_statements_data.append({
                'id':
                stmt.id,
                'text':
                stmt.text[:200] + '...' if len(stmt.text) > 200 else stmt.text,
                'sentiment_score':
                stmt.sentiment_score,
                'speaker_name':
                stmt.speaker.naas_nm,
                'session_id':
                stmt.session.conf_id,
                'created_at':
                stmt.created_at
            })

        party_detail_data = {
            'id': party.id,
            'name': party.name,
            'logo_url': party.logo_url,
            'slogan': party.slogan,
            'description': party.description,
            'member_count': speakers.count(),
            'avg_sentiment': avg_sentiment,
            'total_statements': statements.count(),
            'positive_statements': positive_statements,
            'negative_statements': negative_statements,
            'neutral_statements': neutral_statements,
            'total_bills': bills.count(),
            'recent_statements': recent_statements_data,
            'created_at': party.created_at,
            'updated_at': party.updated_at,
            'additional_data_fetched': fetch_additional
        }

        return Response({'status': 'success', 'data': party_detail_data})

    except Exception as e:
        return Response(
            {
                'status': 'error',
                'message': f'정당 상세 정보를 불러오는 중 오류가 발생했습니다: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def sentiment_analysis_list(request):
    """Get list of sentiment analysis data"""
    try:
        time_range = request.query_params.get('time_range', 'all')

        # Base queryset for statements
        statements_qs = Statement.objects.select_related(
            'speaker', 'session', 'bill').all()

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))
        elif time_range == 'week':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=7))

        # Get sentiment analysis data grouped by different dimensions
        results = []

        # By speaker sentiment
        speaker_sentiment = statements_qs.values(
            'speaker__naas_nm', 'speaker__plpt_nm').annotate(
                avg_sentiment=Avg('sentiment_score'),
                statement_count=Count('id'),
                positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
                negative_count=Count(
                    'id', filter=Q(sentiment_score__lt=-0.3))).filter(
                        statement_count__gte=3).order_by('-avg_sentiment')[:20]

        for speaker in speaker_sentiment:
            results.append({
                'type':
                'speaker',
                'name':
                speaker['speaker__naas_nm'],
                'party':
                speaker['speaker__plpt_nm'],
                'avg_sentiment':
                round(speaker['avg_sentiment'] or 0, 3),
                'statement_count':
                speaker['statement_count'],
                'positive_count':
                speaker['positive_count'],
                'negative_count':
                speaker['negative_count']
            })

        return Response(results)

    except Exception as e:
        logger.error(f"Error in sentiment_analysis_list: {e}")
        return Response([], status=200)


@api_view(['GET'])
def session_sentiment_by_party(request, pk):
    """Get sentiment analysis by party for a specific session"""
    try:
        session = get_object_or_404(Session, conf_id=pk)

        # Get statements for this session
        statements = Statement.objects.filter(
            session=session,
            sentiment_score__isnull=False).select_related('speaker')

        if not statements.exists():
            return Response({
                'session': {
                    'id': session.conf_id,
                    'title': session.title,
                    'date': session.conf_dt
                },
                'party_sentiment': [],
                'total_statements': 0
            })

        # Group by party and calculate sentiment
        party_sentiment = {}

        for statement in statements:
            party_name = statement.speaker.get_current_party_name()

            # Skip invalid parties
            if not party_name or party_name in ['정보없음', '', ' ', '무소속']:
                continue

            if party_name not in party_sentiment:
                party_sentiment[party_name] = {
                    'party_name': party_name,
                    'statements': [],
                    'statement_count': 0,
                    'avg_sentiment': 0,
                    'positive_count': 0,
                    'negative_count': 0,
                    'neutral_count': 0
                }

            party_sentiment[party_name]['statements'].append(
                statement.sentiment_score)
            party_sentiment[party_name]['statement_count'] += 1

            if statement.sentiment_score > 0.3:
                party_sentiment[party_name]['positive_count'] += 1
            elif statement.sentiment_score < -0.3:
                party_sentiment[party_name]['negative_count'] += 1
            else:
                party_sentiment[party_name]['neutral_count'] += 1

        # Calculate averages
        results = []
        for party_data in party_sentiment.values():
            if party_data['statements']:
                party_data['avg_sentiment'] = round(
                    sum(party_data['statements']) /
                    len(party_data['statements']), 3)
                del party_data['statements']  # Remove raw data
                results.append(party_data)

        # Sort by average sentiment
        results.sort(key=lambda x: x['avg_sentiment'], reverse=True)

        return Response({
            'session': {
                'id': session.conf_id,
                'title': session.title,
                'date': session.conf_dt
            },
            'party_sentiment': results,
            'total_statements': statements.count()
        })

    except Exception as e:
        logger.error(f"Error in session_sentiment_by_party: {e}")
        return Response(
            {
                'session': {
                    'id': pk,
                    'title': None,
                    'date': None
                },
                'party_sentiment': [],
                'total_statements': 0
            },
            status=200)


@api_view(['GET'])
def party_analytics(request):
    """Get analytics data grouped by parties"""
    try:
        time_range = request.query_params.get('time_range', 'all')
        categories = request.query_params.get('categories')

        # Base queryset for statements
        statements_qs = Statement.objects.filter(
            session__era_co__in=['제22대', '22']).select_related(
                'speaker', 'session', 'bill')

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))

        # Apply category filter if provided
        if categories:
            category_ids = [
                int(id.strip()) for id in categories.split(',') if id.strip()
            ]
            statements_qs = statements_qs.filter(
                categories__category_id__in=category_ids)

        # Get party analytics
        party_stats = statements_qs.values('speaker__plpt_nm').annotate(
            party_name=F('speaker__plpt_nm'),
            statement_count=Count('id'),
            avg_sentiment=Avg('sentiment_score'),
            positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
            negative_count=Count(
                'id', filter=Q(sentiment_score__lt=-0.3))).filter(
                    statement_count__gt=0).order_by('-statement_count')

        # Clean up party names and add member counts
        results = []
        for party in party_stats:
            if not party['party_name'] or party['party_name'] in [
                    '', ' ', '무소속', '정보없음'
            ]:
                continue

            member_count = Speaker.objects.filter(
                plpt_nm__icontains=party['party_name'],
                gtelt_eraco__icontains='22').count()

            neutral_count = party['statement_count'] - party[
                'positive_count'] - party['negative_count']

            results.append({
                'party_name':
                party['party_name'],
                'member_count':
                member_count,
                'statement_count':
                party['statement_count'],
                'avg_sentiment':
                round(party['avg_sentiment'] or 0, 3),
                'positive_count':
                party['positive_count'],
                'negative_count':
                party['negative_count'],
                'neutral_count':
                neutral_count,
                'positive_percentage':
                round((party['positive_count'] / party['statement_count']) *
                      100, 1) if party['statement_count'] > 0 else 0,
                'negative_percentage':
                round((party['negative_count'] / party['statement_count']) *
                      100, 1) if party['statement_count'] > 0 else 0
            })

        return Response({
            'time_range': time_range,
            'results': results,
            'total_parties': len(results)
        })

    except Exception as e:
        logger.error(f"Error in party analytics: {e}")
        return Response({'error': 'Failed to fetch party analytics'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def overall_analytics(request):
    """Get overall system analytics and statistics"""
    try:
        time_range = request.query_params.get('time_range', 'all')

        # Base querysets for 22nd Assembly
        sessions_qs = Session.objects.filter(era_co__in=['제22대', '22'])
        bills_qs = Bill.objects.filter(session__era_co__in=['제22대', '22'])
        speakers_qs = Speaker.objects.filter(gtelt_eraco__icontains='22')
        statements_qs = Statement.objects.filter(
            session__era_co__in=['제22대', '22'])

        # Apply time filter
        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=365))
            sessions_qs = sessions_qs.filter(conf_dt__gte=now.date() -
                                             timedelta(days=365))
            bills_qs = bills_qs.filter(session__conf_dt__gte=now.date() -
                                       timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(
                session__conf_dt__gte=now.date() - timedelta(days=30))
            sessions_qs = sessions_qs.filter(conf_dt__gte=now.date() -
                                             timedelta(days=30))
            bills_qs = bills_qs.filter(session__conf_dt__gte=now.date() -
                                       timedelta(days=30))

        # Basic counts
        total_sessions = sessions_qs.count()
        total_bills = bills_qs.count()
        total_speakers = speakers_qs.count()
        total_statements = statements_qs.count()

        # Sentiment analysis
        sentiment_stats = statements_qs.aggregate(
            avg_sentiment=Avg('sentiment_score'),
            positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
            negative_count=Count('id', filter=Q(sentiment_score__lt=-0.3)))

        avg_sentiment = sentiment_stats['avg_sentiment'] or 0
        positive_count = sentiment_stats['positive_count'] or 0
        negative_count = sentiment_stats['negative_count'] or 0
        neutral_count = total_statements - positive_count - negative_count

        # Recent activity
        recent_activity = {
            'recent_sessions':
            sessions_qs.order_by('-conf_dt')[:5].values(
                'conf_id', 'title', 'conf_dt'),
            'recent_bills':
            bills_qs.order_by('-created_at')[:5].values(
                'bill_id', 'bill_nm', 'proposer'),
            'recent_statements':
            statements_qs.order_by('-created_at')[:10].select_related(
                'speaker').values('id', 'speaker__naas_nm', 'text',
                                  'sentiment_score', 'created_at')
        }

        # Top parties by activity
        top_parties = statements_qs.values('speaker__plpt_nm').annotate(
            party_name=F('speaker__plpt_nm'),
            statement_count=Count('id'),
            avg_sentiment=Avg('sentiment_score')).filter(
                statement_count__gt=5).order_by('-statement_count')[:10]

        return Response({
            'time_range': time_range,
            'overview': {
                'total_sessions': total_sessions,
                'total_bills': total_bills,
                'total_speakers': total_speakers,
                'total_statements': total_statements
            },
            'sentiment_analysis': {
                'average_sentiment':
                round(avg_sentiment, 3),
                'positive_count':
                positive_count,
                'negative_count':
                negative_count,
                'neutral_count':
                neutral_count,
                'positive_percentage':
                round((positive_count / total_statements) *
                      100, 1) if total_statements > 0 else 0,
                'negative_percentage':
                round((negative_count / total_statements) *
                      100, 1) if total_statements > 0 else 0
            },
            'recent_activity': {
                'recent_sessions': list(recent_activity['recent_sessions']),
                'recent_bills': list(recent_activity['recent_bills']),
                'recent_statements': list(recent_activity['recent_statements'])
            },
            'top_parties': list(top_parties)
        })

    except Exception as e:
        logger.error(f"Error in overall analytics: {e}")
        return Response({'error': 'Failed to fetch overall analytics'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def stats_overview(request):
    """Get basic statistics overview for DataMetrics component"""
    try:
        # Get basic counts for 22nd Assembly
        sessions_22 = Session.objects.filter(era_co__in=['제22대', '22']).count()
        bills_22 = Bill.objects.filter(
            session__era_co__in=['제22대', '22']).count()
        speakers_22 = Speaker.objects.filter(
            gtelt_eraco__icontains='22').count()
        statements_22 = Statement.objects.filter(
            session__era_co__in=['제22대', '22']).count()
        parties_22 = Party.objects.filter(assembly_era=22).count()

        # If no 22nd Assembly data, get from any assembly
        if sessions_22 == 0:
            sessions_22 = Session.objects.count()
        if bills_22 == 0:
            bills_22 = Bill.objects.count()
        if speakers_22 == 0:
            speakers_22 = Speaker.objects.count()
        if statements_22 == 0:
            statements_22 = Statement.objects.count()
        if parties_22 == 0:
            parties_22 = Party.objects.count()

        return Response({
            'total_sessions': sessions_22,
            'total_bills': bills_22,
            'total_speakers': speakers_22,
            'total_statements': statements_22,
            'total_parties': parties_22
        })

    except Exception as e:
        logger.error(f"Error in stats_overview: {e}")
        return Response(
            {
                'total_sessions': 0,
                'total_bills': 0,
                'total_speakers': 0,
                'total_statements': 0,
                'total_parties': 0
            },
            status=200)


@api_view(['GET'])
def home_data(request):
    """
    API endpoint to get homepage data including recent sessions, bills, and overall statistics
    """
    try:
        # Ensure basic data exists before processing
        data_fetched = ensure_basic_data_exists()
        if data_fetched:
            logger.info("Basic data was fetched during home data request")

        # Get recent sessions - keep it simple and fast
        recent_sessions = Session.objects.filter(
            era_co__in=['22', '제22대']).order_by('-conf_dt')[:5]

        sessions_data = []
        for session in recent_sessions:
            # Count statements for this session
            statement_count = Statement.objects.filter(session=session).count()
            bill_count = Bill.objects.filter(session=session).count()

            # Handle missing session data gracefully
            title = session.title
            if not title:
                era = session.era_co or '22'
                sess = session.sess or '1'
                dgr = session.dgr or '1'
                title = f'제{era}대 제{sess}회 제{dgr}차'

            sessions_data.append({
                'id':
                session.conf_id,
                'title':
                title,
                'date':
                session.conf_dt.isoformat() if session.conf_dt else None,
                'committee':
                session.cmit_nm or '',
                'statement_count':
                statement_count,
                'bill_count':
                bill_count
            })

        # Get recent bills - simple query, ordered by session date
        recent_bills = Bill.objects.filter(
            session__era_co__in=['22', '제22대']).select_related(
                'session').order_by('-session__conf_dt', '-created_at')[:5]

        bills_data = []
        for bill in recent_bills:
            # Count statements for this bill
            statement_count = Statement.objects.filter(bill=bill).count()

            # Clean bill title - remove leading numbers like "10. "
            clean_title = bill.bill_nm
            if clean_title and '. ' in clean_title:
                parts = clean_title.split('. ', 1)
                if parts[0].isdigit():
                    clean_title = parts[1]

            bills_data.append({
                'id':
                bill.bill_id,
                'title':
                clean_title,
                'proposer':
                bill.proposer or '정보없음',
                'session_id':
                bill.session.conf_id if bill.session else None,
                'session_title':
                bill.session.title if bill.session and bill.session.title else
                (f"제{bill.session.era_co}대 제{bill.session.sess}회 제{bill.session.dgr}차"
                 if bill.session else None),
                'statement_count':
                statement_count
            })

        # Get recent statements - simple query
        recent_statements = Statement.objects.filter(
            session__era_co__in=['제22대', '22']).select_related(
                'speaker', 'session', 'bill').order_by('-created_at')[:10]

        statements_data = []
        for statement in recent_statements:
            statements_data.append({
                'id':
                statement.id,
                'speaker_name':
                statement.speaker.naas_nm if statement.speaker else '알 수 없음',
                'speaker_party':
                statement.speaker.get_current_party_name()
                if statement.speaker else '정당정보없음',
                'text':
                statement.text[:200] +
                '...' if len(statement.text) > 200 else statement.text,
                'sentiment_score':
                statement.sentiment_score or 0,
                'session_title':
                statement.session.title
                if statement.session and statement.session.title else None,
                'bill_title':
                statement.bill.bill_nm if statement.bill else None,
                'created_at':
                statement.created_at.isoformat()
                if statement.created_at else None
            })

        # Basic counts - simple queries
        total_sessions = Session.objects.filter(
            era_co__in=['22', '제22대']).count()
        total_bills = Bill.objects.filter(
            session__era_co__in=['22', '제22대']).count()
        total_speakers = Speaker.objects.filter(
            gtelt_eraco__icontains='22').count()
        total_statements = Statement.objects.filter(
            session__era_co__in=['22', '제22대']).count()

        # Calculate sentiment stats
        sentiment_stats = Statement.objects.filter(
            session__era_co__in=['22', '제22대'],
            sentiment_score__isnull=False).aggregate(
                avg_sentiment=Avg('sentiment_score'),
                positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
                negative_count=Count('id', filter=Q(sentiment_score__lt=-0.3)))

        avg_sentiment = sentiment_stats['avg_sentiment'] or 0
        positive_count = sentiment_stats['positive_count'] or 0
        negative_count = sentiment_stats['negative_count'] or 0
        neutral_count = max(0,
                            total_statements - positive_count - negative_count)

        return Response({
            'recent_sessions': sessions_data,
            'recent_bills': bills_data,
            'recent_statements': statements_data,
            'overall_stats': {
                'total_statements': total_statements,
                'average_sentiment': round(avg_sentiment, 3),
                'positive_count': positive_count,
                'neutral_count': neutral_count,
                'negative_count': negative_count
            },
            'party_stats': [],
            'total_sessions': total_sessions,
            'total_bills': total_bills,
            'total_speakers': total_speakers
        })

    except Exception as e:
        logger.error(f"Error in home_data view: {e}")
        return Response(
            {
                'recent_sessions': [],
                'recent_bills': [],
                'recent_statements': [],
                'overall_stats': {
                    'total_statements': 0,
                    'average_sentiment': 0,
                    'positive_count': 0,
                    'neutral_count': 0,
                    'negative_count': 0
                },
                'party_stats': [],
                'total_sessions': 0,
                'total_bills': 0,
                'total_speakers': 0
            },
            status=200)


@api_view(['POST'])
def start_collection(request):
    """Start data collection process"""
    try:
        use_celery = is_celery_available()

        if use_celery:
            from .tasks import fetch_continuous_sessions
            task = fetch_continuous_sessions.delay(force=True, debug=False)
            return JsonResponse({
                'message': 'Collection started asynchronously',
                'task_id': task.id,
                'status': 'started'
            })
        else:
            from .tasks import fetch_continuous_sessions_direct
            try:
                fetch_continuous_sessions_direct(force=True, debug=False)
                return JsonResponse({
                    'message': 'Collection completed successfully',
                    'status': 'completed'
                })
            except Exception as e:
                return JsonResponse(
                    {
                        'message': f'Collection failed: {str(e)}',
                        'status': 'failed'
                    },
                    status=500)

    except Exception as e:
        return JsonResponse({'error': f'Failed to start collection: {str(e)}'},
                            status=500)
