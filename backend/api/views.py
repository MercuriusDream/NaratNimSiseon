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
                          PartySerializer, CategorySerializer, VotingRecordSerializer)
from .llm_analyzer import LLMPolicyAnalyzer
import logging
from django.utils import timezone
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.db.models import Count, Avg
from datetime import datetime, timedelta
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db import models

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

    def get_queryset(self):
        queryset = super().get_queryset()
        era_co = self.request.query_params.get('era_co')
        sess = self.request.query_params.get('sess')
        dgr = self.request.query_params.get('dgr')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if era_co:
            queryset = queryset.filter(era_co=era_co)
        if sess:
            queryset = queryset.filter(sess=sess)
        if dgr:
            queryset = queryset.filter(dgr=dgr)
        if date_from:
            queryset = queryset.filter(conf_dt__gte=date_from)
        if date_to:
            queryset = queryset.filter(conf_dt__lte=date_to)

        return queryset.order_by('-conf_dt')

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
        statements = session.statements.all()
        serializer = StatementSerializer(statements, many=True)
        return Response({'status': 'success', 'data': serializer.data})


class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    pagination_class = StandardResultsSetPagination

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to ensure consistent response format"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving bill {kwargs.get('pk')}: {e}")
            return Response({
                'status': 'error',
                'message': 'Failed to retrieve bill'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_queryset(self):
        queryset = super().get_queryset()
        bill_name = self.request.query_params.get('bill_name')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if bill_name:
            queryset = queryset.filter(bill_nm__icontains=bill_name)
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        return queryset.order_by('-created_at')

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
            voting_records = VotingRecord.objects.filter(bill=bill) if hasattr(VotingRecord, 'objects') else VotingRecord.objects.none()

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

                if speaker_name not in combined_sentiment[party_name]['members']:
                    combined_sentiment[party_name]['members'][speaker_name] = {
                        'speaker_name': speaker_name,
                        'statements': [],
                        'vote_result': None,
                        'vote_sentiment': 0,
                        'avg_statement_sentiment': 0,
                        'combined_sentiment': 0
                    }

                combined_sentiment[party_name]['members'][speaker_name]['statements'].append({
                    'text': statement.text[:200] + '...' if len(statement.text) > 200 else statement.text,
                    'sentiment_score': statement.sentiment_score or 0,
                    'created_at': statement.created_at
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

                if speaker_name not in combined_sentiment[party_name]['members']:
                    combined_sentiment[party_name]['members'][speaker_name] = {
                        'speaker_name': speaker_name,
                        'statements': [],
                        'vote_result': None,
                        'vote_sentiment': 0,
                        'avg_statement_sentiment': 0,
                        'combined_sentiment': 0
                    }

                combined_sentiment[party_name]['members'][speaker_name]['vote_result'] = vote.vote_result
                combined_sentiment[party_name]['members'][speaker_name]['vote_sentiment'] = vote.sentiment_score
                combined_sentiment[party_name]['voting_count'] += 1

            # Calculate averages and combined sentiment
            for party_data in combined_sentiment.values():
                statement_sentiments = []
                voting_sentiments = []

                for member_data in party_data['members'].values():
                    # Calculate average statement sentiment for member
                    if member_data['statements']:
                        member_statement_avg = sum(s['sentiment_score'] for s in member_data['statements']) / len(member_data['statements'])
                        member_data['avg_statement_sentiment'] = round(member_statement_avg, 3)
                        statement_sentiments.append(member_statement_avg)

                    # Add voting sentiment
                    if member_data['vote_result']:
                        voting_sentiments.append(member_data['vote_sentiment'])

                    # Calculate combined sentiment (weighted average of statements and voting)
                    statement_weight = 0.6 if member_data['statements'] else 0
                    voting_weight = 0.4 if member_data['vote_result'] else 0

                    if statement_weight > 0 and voting_weight > 0:
                        member_data['combined_sentiment'] = round(
                            (member_data['avg_statement_sentiment'] * statement_weight + 
                             member_data['vote_sentiment'] * voting_weight), 3)
                    elif statement_weight > 0:
                        member_data['combined_sentiment'] = member_data['avg_statement_sentiment']
                    elif voting_weight > 0:
                        member_data['combined_sentiment'] = member_data['vote_sentiment']

                # Calculate party averages
                if statement_sentiments:
                    party_data['avg_statement_sentiment'] = round(sum(statement_sentiments) / len(statement_sentiments), 3)
                if voting_sentiments:
                    party_data['avg_voting_sentiment'] = round(sum(voting_sentiments) / len(voting_sentiments), 3)

                # Calculate combined party sentiment
                all_member_sentiments = [m['combined_sentiment'] for m in party_data['members'].values() if m['combined_sentiment'] != 0]
                if all_member_sentiments:
                    party_data['combined_sentiment'] = round(sum(all_member_sentiments) / len(all_member_sentiments), 3)

            # Convert to list and sort by combined sentiment
            party_list = list(combined_sentiment.values())
            party_list.sort(key=lambda x: x['combined_sentiment'], reverse=True)

            # Calculate overall statistics
            total_voting_records = voting_records.count()
            vote_distribution = voting_records.values('vote_result').annotate(count=Count('id')) if voting_records.exists() else []

            return Response({
                'bill': {
                    'id': bill.bill_id,
                    'name': bill.bill_nm,
                    'session_date': bill.session.conf_dt if bill.session else None
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
            return Response({'error': 'Failed to fetch bill voting sentiment analysis'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def sentiment(self, request, pk=None):
        """Get detailed sentiment analysis for a specific bill"""
        try:
            bill = self.get_object()
            statements = Statement.objects.filter(bill=bill)

            if not statements.exists():
                return Response({
                    'bill': {
                        'id': bill.bill_id,
                        'name': bill.bill_nm
                    },
                    'sentiment_summary': {
                        'total_statements': 0,
                        'average_sentiment': 0,
                        'positive_count': 0,
                        'neutral_count': 0,
                        'negative_count': 0
                    },
                    'party_breakdown': [],
                    'speaker_breakdown': [],
                    'sentiment_timeline': []
                })

            # Calculate sentiment summary
            total_statements = statements.count()
            average_sentiment = statements.aggregate(
                avg=Avg('sentiment_score'))['avg'] or 0
            positive_count = statements.filter(sentiment_score__gt=0.3).count()
            negative_count = statements.filter(sentiment_score__lt=-0.3).count()
            neutral_count = total_statements - positive_count - negative_count

            # Party breakdown
            party_breakdown = statements.values('speaker__plpt_nm').annotate(
                count=Count('id'),
                avg_sentiment=Avg('sentiment_score'),
                positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
                negative_count=Count(
                    'id',
                    filter=Q(sentiment_score__lt=-0.3))).order_by('-avg_sentiment')

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
        queryset = super().get_queryset()
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
        if era_co:
            queryset = queryset.filter(era_co=era_co)

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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
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
            fetch_additional = request.query_params.get('fetch_additional', 'false').lower() == 'true'

            if fetch_additional:
                try:
                    from .tasks import fetch_additional_data_nepjpxkkabqiqpbvk
                    if is_celery_available():
                        fetch_additional_data_nepjpxkkabqiqpbvk.delay()
                    else:
                        fetch_additional_data_nepjpxkkabqiqpbvk()
                except Exception as e:
                    logger.error(f"Error triggering additional data fetch: {e}")

            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)

            data = serializer.data if serializer.data is not None else []

            response_data = {
                'results': data,
                'count': len(data)
            }

            if fetch_additional:
                response_data['additional_data_fetched'] = True

            return Response(response_data)

        except Exception as e:
            logger.error(f"Error in PartyViewSet list: {e}")
            return Response([])


class StatementListView(generics.ListAPIView):
    serializer_class = StatementSerializer

    def get_queryset(self):
        bill_id = self.kwargs.get('bill_id')
        return Statement.objects.filter(bill_id=bill_id)


@api_view(['GET'])
def statement_list(request):
    """List all statements with pagination and filtering"""
    try:
        statements_qs = Statement.objects.select_related(
            'speaker', 'session', 'bill').all()

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
        bills_qs = Bill.objects.select_related('session').all()

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

        # Pagination
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(bills_qs.order_by('-created_at'),
                                           request)
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
                round(latest_statement.sentiment_score, 2)
                if latest_statement and latest_statement.sentiment_score else None
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

        # Base queryset for statements
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
                monthly_data[month_key]['sentiment_scores'].append(statement.sentiment_score)

        # Calculate monthly averages
        trend_data = []
        for month, data in sorted(monthly_data.items()):
            if data['sentiment_scores']:
                avg_sentiment = sum(data['sentiment_scores']) / len(data['sentiment_scores'])
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

        statements_qs = Statement.objects.all()

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

        if not statements_qs.exists():
            return Response({
                'message': 'No statements found for the specified time range',
                'stats': {}
            })

        # Overall statistics
        total_statements = statements_qs.count()
        avg_sentiment = statements_qs.aggregate(
            avg=Avg('sentiment_score'))['avg'] or 0

        # Sentiment distribution
        positive_count = statements_qs.filter(sentiment_score__gt=0.3).count()
        negative_count = statements_qs.filter(sentiment_score__lt=-0.3).count()
        neutral_count = total_statements - positive_count - negative_count

        # Party sentiment ranking
        party_stats = statements_qs.values('speaker__plpt_nm').annotate(
            avg_sentiment=Avg('sentiment_score'),
            statement_count=Count('id'),
            positive_count=Count('id', filter=Q(sentiment_score__gt=0.3)),
            negative_count=Count(
                'id', filter=Q(sentiment_score__lt=-0.3))).filter(
                    statement_count__gte=5).order_by('-avg_sentiment')

        # Most active speakers
        speaker_stats = statements_qs.values(
            'speaker__naas_nm', 'speaker__plpt_nm').annotate(
                avg_sentiment=Avg('sentiment_score'),
                statement_count=Count('id')).filter(
                    statement_count__gte=3).order_by('-statement_count')[:20]

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
                round((positive_count / total_statements) * 100, 1),
                'negative_percentage':
                round((negative_count / total_statements) * 100, 1)
            },
            'party_rankings': list(party_stats),
            'active_speakers': list(speaker_stats)
        })

    except Exception as e:
        logger.error(f"Error in overall sentiment stats: {e}")
        return Response({'error': 'Failed to fetch sentiment statistics'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def sentiment_by_party_and_topic(request):
    """Get sentiment analysis grouped by party and topic/bill"""
    try:
        group_by = request.query_params.get('group_by', 'bill')  # 'bill' or 'topic'
        time_range = request.query_params.get('time_range', 'all')

        # Base queryset for statements
        statements_qs = Statement.objects.select_related('speaker', 'bill', 'session').all()

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

            for statement in statements_qs.filter(sentiment_score__isnull=False, bill__isnull=False):
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

                party_bill_data[key]['sentiment_scores'].append(statement.sentiment_score)
                party_bill_data[key]['statement_count'] += 1

            # Calculate averages
            for data in party_bill_data.values():
                if data['sentiment_scores']:
                    data['avg_sentiment'] = round(sum(data['sentiment_scores']) / len(data['sentiment_scores']), 3)
                    data['positive_count'] = len([s for s in data['sentiment_scores'] if s > 0.3])
                    data['negative_count'] = len([s for s in data['sentiment_scores'] if s < -0.3])
                    data['neutral_count'] = data['statement_count'] - data['positive_count'] - data['negative_count']
                    results.append(data)

        else:  # group_by == 'topic'
            # Group by party and topic (category)
            party_topic_data = {}

            for statement in statements_qs.filter(sentiment_score__isnull=False, categories__isnull=False).distinct():
                party_name = statement.speaker.get_current_party_name()

                for category_relation in statement.categories.all():
                    topic_name = category_relation.category.name

                    key = f"{party_name}|{topic_name}"
                    if key not in party_topic_data:
                        party_topic_data[key] = {
                            'party_name': party_name,
                            'topic_name': topic_name,
                            'sentiment_scores': [],
                            'statement_count': 0
                        }

                    party_topic_data[key]['sentiment_scores'].append(statement.sentiment_score)
                    party_topic_data[key]['statement_count'] += 1

            # Calculate averages
            for data in party_topic_data.values():
                if data['sentiment_scores']:
                    data['avg_sentiment'] = round(sum(data['sentiment_scores']) / len(data['sentiment_scores']), 3)
                    data['positive_count'] = len([s for s in data['sentiment_scores'] if s > 0.3])
                    data['negative_count'] = len([s for s in data['sentiment_scores'] if s < -0.3])
                    data['neutral_count'] = data['statement_count'] - data['positive_count'] - data['negative_count']
                    results.append(data)

        # Sort by average sentiment (descending)
        results.sort(key=lambda x: x.get('avg_sentiment', 0), reverse=True)

        return Response({
            'group_by': group_by,
            'time_range': time_range,
            'results': results,
            'total_entries': len(results)
        })

    except Exception as e:
        logger.error(f"Error in sentiment_by_party_and_topic: {e}")
        return Response({'error': 'Failed to fetch sentiment analysis'}, 
                       status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def category_sentiment_analysis(request):
    """Get sentiment analysis by categories and subcategories"""
    try:
        time_range = request.query_params.get('time_range', 'all')
        party_filter = request.query_params.get('party')
        category_filter = request.query_params.get('category')

        # Base queryset for statements with categories
        statements_qs = Statement.objects.filter(categories__isnull=False).distinct()

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
            statements_qs = statements_qs.filter(speaker__plpt_nm__icontains=party_filter)

        # Apply category filter
        if category_filter:
            statements_qs = statements_qs.filter(categories__category__name=category_filter)

        # Get category-wise sentiment analysis
        category_data = []
        for category in Category.objects.all():
            category_statements = statements_qs.filter(categories__category=category)

            if not category_statements.exists():
                continue

            avg_sentiment = category_statements.aggregate(
                avg_sentiment=Avg('sentiment_score'))['avg_sentiment'] or 0

            statement_count = category_statements.count()
            positive_count = category_statements.filter(sentiment_score__gt=0.3).count()
            negative_count = category_statements.filter(sentiment_score__lt=-0.3).count()
            neutral_count = statement_count - positive_count - negative_count

            # Get party breakdown for this category
            party_breakdown = category_statements.values('speaker__plpt_nm').annotate(
                count=Count('id'),
                avg_sentiment=Avg('sentiment_score')
            ).order_by('-avg_sentiment')[:10]

            # Get subcategory breakdown
            subcategory_breakdown = []
            for subcategory in category.subcategories.all():
                subcat_statements = category_statements.filter(categories__subcategory=subcategory)
                if subcat_statements.exists():
                    subcategory_breakdown.append({
                        'subcategory_id': subcategory.id,
                        'subcategory_name': subcategory.name,
                        'statement_count': subcat_statements.count(),
                        'avg_sentiment': round(subcat_statements.aggregate(
                            avg=Avg('sentiment_score'))['avg'] or 0, 3)
                    })

            category_data.append({
                'category_id': category.id,
                'category_name': category.name,
                'statement_count': statement_count,
                'avg_sentiment': round(avg_sentiment, 3),
                'positive_count': positive_count,
                'negative_count': negative_count,
                'neutral_count': neutral_count,
                'positive_percentage': round((positive_count / statement_count) * 100, 1),
                'negative_percentage': round((negative_count / statement_count) * 100, 1),
                'party_breakdown': list(party_breakdown),
                'subcategory_breakdown': subcategory_breakdown
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
        return Response({'error': 'Failed to fetch category sentiment analysis'},
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
            all_speakers = Speaker.objects.filter(plpt_nm__icontains=party.name)
            member_count = all_speakers.count()

            # Skip if no members found
            if member_count == 0:
                continue

            # Get statements and sentiment analysis
            statements = Statement.objects.filter(speaker__plpt_nm__icontains=party.name)
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
def home_data(request):
    """Get aggregated data for home page"""
    try:
        # Get recent sessions
        recent_sessions = Session.objects.order_by('-conf_dt')[:5]
        sessions_data = []
        for session in recent_sessions:
            sessions_data.append({
                'id': session.conf_id,
                'title': session.title or f'제{session.era_co} {session.sess}회 {session.dgr}차',
                'date': session.conf_dt,
                'committee': session.cmit_nm,
                'statement_count': session.statements.count(),
                'bill_count': session.bills.count()
            })

        # Get recent bills
        recent_bills = Bill.objects.order_by('-created_at')[:5]
        bills_data = []
        for bill in recent_bills:
            bills_data.append({
                'id': bill.bill_id,
                'title': bill.bill_nm,
                'proposer': bill.proposer,
                'session_id': bill.session.conf_id if bill.session else None,
                'session_title': bill.session.title if bill.session else None,
                'statement_count': bill.statements.count() if hasattr(bill, 'statements') else 0
            })

        # Get recent statements with sentiment analysis
        recent_statements = Statement.objects.select_related('speaker', 'session', 'bill').order_by('-created_at')[:10]
        statements_data = []
        for statement in recent_statements:
            statements_data.append({
                'id': statement.id,
                'speaker_name': statement.speaker.naas_nm,
                'speaker_party': statement.speaker.get_current_party_name(),
                'text': statement.text[:200] + '...' if len(statement.text) > 200 else statement.text,
                'sentiment_score': statement.sentiment_score or 0,
                'sentiment_reason': statement.sentiment_reason or '',
                'bill_relevance_score': statement.bill_relevance_score or 0,
                'session_title': statement.session.title if statement.session else None,
                'bill_title': statement.bill.bill_nm if statement.bill else None,
                'created_at': statement.created_at
            })

        # Calculate overall sentiment stats
        all_statements = Statement.objects.all()
        total_statements = all_statements.count()

        if total_statements > 0:
            avg_sentiment = all_statements.aggregate(
                avg_sentiment=models.Avg('sentiment_score')
            )['avg_sentiment'] or 0

            positive_count = all_statements.filter(sentiment_score__gt=0.3).count()
            neutral_count = all_statements.filter(
                sentiment_score__gte=-0.3, 
                sentiment_score__lte=0.3
            ).count()
            negative_count = all_statements.filter(sentiment_score__lt=-0.3).count()
        else:
            avg_sentiment = 0
            positive_count = 0
            neutral_count = 0
            negative_count = 0

        # Get party statistics
        parties = Party.objects.all()
        party_stats = []
        for party in parties:
            party_statements = Statement.objects.filter(
                speaker__current_party=party
            )

            if party_statements.exists():
                avg_party_sentiment = party_statements.aggregate(
                    avg_sentiment=models.Avg('sentiment_score')
                )['avg_sentiment'] or 0

                party_stats.append({
                    'party_name': party.name,
                    'member_count': party.members.count(),
                    'statement_count': party_statements.count(),
                    'avg_sentiment': avg_party_sentiment
                })

        return Response({
            'recent_sessions': sessions_data,
            'recent_bills': bills_data,
            'recent_statements': statements_data,
            'overall_stats': {
                'total_statements': total_statements,
                'average_sentiment': avg_sentiment,
                'positive_count': positive_count,
                'neutral_count': neutral_count,
                'negative_count': negative_count
            },
            'party_stats': party_stats,
            'total_sessions': Session.objects.count(),
            'total_bills': Bill.objects.count(),
            'total_speakers': Speaker.objects.count()
        })

    except Exception as e:
        logger.error(f"Error in home_data view: {e}")
        return Response(
            {'error': 'Failed to fetch home data'}, 
            status=500
        )