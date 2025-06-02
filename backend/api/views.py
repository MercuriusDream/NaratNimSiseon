from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotFound, PermissionDenied
from .models import Session, Bill, Speaker, Statement
from .serializers import (
    SessionSerializer, BillSerializer, SpeakerSerializer,
    StatementSerializer, StatementCreateSerializer
)
import logging
from django.utils import timezone
from django.db.models import Q
from rest_framework.pagination import PageNumberPagination

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
    def bills(self, request, pk=None):
        try:
            session = self.get_object()
            bills = session.bills.all()
            serializer = BillSerializer(bills, many=True)
            return Response({
                'status': 'success',
                'data': serializer.data
            })
        except Exception as e:
            logger.error(f"Error fetching bills for session {pk}: {e}")
            return Response({
                'status': 'error',
                'message': '의안 목록을 불러오는 중 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        try:
            session = self.get_object()
            statements = session.statements.all()
            serializer = StatementSerializer(statements, many=True)
            return Response({
                'status': 'success',
                'data': serializer.data
            })
        except Exception as e:
            logger.error(f"Error fetching statements for session {pk}: {e}")
            return Response({
                'status': 'error',
                'message': '발언 목록을 불러오는 중 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        bill_name = self.request.query_params.get('bill_name')
        proposer = self.request.query_params.get('proposer')
        status = self.request.query_params.get('status')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if bill_name:
            queryset = queryset.filter(bill_nm__icontains=bill_name)
        if proposer:
            queryset = queryset.filter(proposer__icontains=proposer)
        if status:
            queryset = queryset.filter(status=status)
        if date_from:
            queryset = queryset.filter(proposal_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(proposal_date__lte=date_to)

        return queryset.order_by('-proposal_date')

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        try:
            bill = self.get_object()
            statements = bill.statements.all()
            serializer = StatementSerializer(statements, many=True)
            return Response({
                'status': 'success',
                'data': serializer.data
            })
        except Exception as e:
            logger.error(f"Error fetching statements for bill {pk}: {e}")
            return Response({
                'status': 'error',
                'message': '발언 목록을 불러오는 중 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SpeakerViewSet(viewsets.ModelViewSet):
    queryset = Speaker.objects.all()
    serializer_class = SpeakerSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        name = self.request.query_params.get('name')
        party = self.request.query_params.get('party')
        constituency = self.request.query_params.get('constituency')
        era_co = self.request.query_params.get('era_co')

        if name:
            queryset = queryset.filter(naas_nm__icontains=name)
        if party:
            queryset = queryset.filter(plpt_nm__icontains=party)
        if constituency:
            queryset = queryset.filter(constituency__icontains=constituency)
        if era_co:
            queryset = queryset.filter(era_co=era_co)

        return queryset.order_by('naas_nm')

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        try:
            speaker = self.get_object()
            time_range = request.query_params.get('time_range', 'all')
            
            statements = speaker.statements.all()
            if time_range == 'year':
                statements = statements.filter(session__conf_dt__gte=timezone.now() - timezone.timedelta(days=365))
            elif time_range == 'month':
                statements = statements.filter(session__conf_dt__gte=timezone.now() - timezone.timedelta(days=30))
                
            serializer = StatementSerializer(statements, many=True)
            return Response({
                'status': 'success',
                'data': serializer.data
            })
        except Exception as e:
            logger.error(f"Error fetching statements for speaker {pk}: {e}")
            return Response({
                'status': 'error',
                'message': '발언 목록을 불러오는 중 오류가 발생했습니다.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
