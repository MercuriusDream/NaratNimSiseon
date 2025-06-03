from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework.exceptions import NotFound, PermissionDenied
from .models import Session, Bill, Speaker, Statement, Party # Added Party model
from .utils import api_action_wrapper # Import the decorator
from .serializers import (
    SessionSerializer, BillSerializer, SpeakerSerializer,
    StatementSerializer, StatementCreateSerializer, PartySerializer # Added PartySerializer
)
import logging
from django.utils import timezone
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.db.models import Count, Avg
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

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
    @api_action_wrapper(log_prefix="Fetching bills for session", default_error_message='의안 목록을 불러오는 중 오류가 발생했습니다.')
    def bills(self, request, pk=None):
        session = self.get_object()
        bills = session.bills.all()
        # TODO: Consider pagination for this action as well
        # page = self.paginate_queryset(bills.order_by('-created_at'))
        # if page is not None:
        #     serializer = BillSerializer(page, many=True)
        #     return self.get_paginated_response(serializer.data) # This would not match current success/data structure
        serializer = BillSerializer(bills, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data
        })

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching statements for session", default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        session = self.get_object()
        statements = session.statements.all()
        # TODO: Consider pagination
        serializer = StatementSerializer(statements, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data
        })

class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    pagination_class = StandardResultsSetPagination

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
    @api_action_wrapper(log_prefix="Fetching statements for bill", default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        bill = self.get_object()
        statements = bill.statements.all()
        # TODO: Consider pagination
        serializer = StatementSerializer(statements, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data
        })

class SpeakerViewSet(viewsets.ModelViewSet):
    queryset = Speaker.objects.all()
    serializer_class = SpeakerSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        name = self.request.query_params.get('name')
        party = self.request.query_params.get('party')
        elecd_nm_param = self.request.query_params.get('elecd_nm') # Corrected parameter name
        era_co = self.request.query_params.get('era_co')

        if name:
            queryset = queryset.filter(naas_nm__icontains=name)
        if party:
            queryset = queryset.filter(plpt_nm__icontains=party)
        if elecd_nm_param: # Use corrected parameter
            queryset = queryset.filter(elecd_nm__icontains=elecd_nm_param) # Filter by elecd_nm
        if era_co:
            queryset = queryset.filter(era_co=era_co)

        return queryset.order_by('naas_nm')

    @action(detail=True, methods=['get'])
    @api_action_wrapper(log_prefix="Fetching statements for speaker", default_error_message='발언 목록을 불러오는 중 오류가 발생했습니다.')
    def statements(self, request, pk=None):
        speaker = self.get_object() # Http404 will be caught by the wrapper
        time_range = request.query_params.get('time_range', 'all')

        statements_qs = speaker.statements.all()

        now = timezone.now()
        if time_range == 'year':
            statements_qs = statements_qs.filter(session__conf_dt__gte=now.date() - timezone.timedelta(days=365))
        elif time_range == 'month':
            statements_qs = statements_qs.filter(session__conf_dt__gte=now.date() - timezone.timedelta(days=30))

        ordered_statements = statements_qs.order_by('-session__conf_dt', '-created_at')

        page = self.paginate_queryset(ordered_statements)
        if page is not None:
            serializer = StatementSerializer(page, many=True)
            # This will use the default paginated response structure (count, next, previous, results)
            return self.get_paginated_response(serializer.data)

        # Non-paginated response, or if pagination is not triggered.
        # To keep the {'status': 'success', 'data': ...} structure, we send it like this.
        # If paginated, the wrapper will return DRF's default paginated structure.
        # This means the response structure will differ based on whether it's paginated or not for this action.
        serializer = StatementSerializer(ordered_statements, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data
        })

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
            return Response({
                'status': 'success',
                'data': StatementSerializer(serializer.instance).data
            }, status=status.HTTP_201_CREATED, headers=headers)
        except ValidationError as e:
            logger.error(f"Validation error creating statement: {e}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating statement: {e}")
            return Response({
                'status': 'error',
                'message': '발언을 생성하는 중 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PartyViewSet(viewsets.ModelViewSet):
    queryset = Party.objects.all()
    serializer_class = PartySerializer
    pagination_class = StandardResultsSetPagination

class StatementListView(generics.ListAPIView):
    serializer_class = StatementSerializer

    def get_queryset(self):
        bill_id = self.kwargs.get('bill_id')
        return Statement.objects.filter(bill_id=bill_id)

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
    recent_statements = Statement.objects.filter(created_at__gte=yesterday).count()

    # Processing status
    sessions_with_statements = Session.objects.annotate(
        statement_count=Count('statements')
    ).filter(statement_count__gt=0).count()

    sessions_with_pdfs = Session.objects.exclude(down_url='').count()

    processing_rate = 0
    if session_count > 0:
        processing_rate = (sessions_with_statements / session_count) * 100

    # Sentiment analysis
    sentiment_data = {}
    if statement_count > 0:
        avg_sentiment = Statement.objects.aggregate(
            avg_sentiment=Avg('sentiment_score')
        )['avg_sentiment']

        positive_statements = Statement.objects.filter(sentiment_score__gt=0.3).count()
        negative_statements = Statement.objects.filter(sentiment_score__lt=-0.3).count()
        neutral_statements = statement_count - positive_statements - negative_statements

        sentiment_data = {
            'average_sentiment': round(avg_sentiment, 3) if avg_sentiment else 0,
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
                'created_at': latest_session.created_at if latest_session else None
            },
            'latest_statement': {
                'created_at': latest_statement.created_at if latest_statement else None,
                'speaker': latest_statement.speaker.naas_nm if latest_statement else None,
                'sentiment': round(latest_statement.sentiment_score, 2) if latest_statement else None
            }
        },
        'last_updated': datetime.now()
    })