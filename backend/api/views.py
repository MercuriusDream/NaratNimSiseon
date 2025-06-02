from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Session, Bill, Speaker, Statement
from .serializers import (
    SessionSerializer, BillSerializer, SpeakerSerializer,
    StatementSerializer, StatementCreateSerializer
)

# Create your views here.

class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer

    @action(detail=True, methods=['get'])
    def bills(self, request, pk=None):
        session = self.get_object()
        bills = session.bills.all()
        serializer = BillSerializer(bills, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        session = self.get_object()
        statements = session.statements.all()
        serializer = StatementSerializer(statements, many=True)
        return Response(serializer.data)

class BillViewSet(viewsets.ModelViewSet):
    queryset = Bill.objects.all()
    serializer_class = BillSerializer

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        bill = self.get_object()
        statements = bill.statements.all()
        serializer = StatementSerializer(statements, many=True)
        return Response(serializer.data)

class SpeakerViewSet(viewsets.ModelViewSet):
    queryset = Speaker.objects.all()
    serializer_class = SpeakerSerializer

    @action(detail=True, methods=['get'])
    def statements(self, request, pk=None):
        speaker = self.get_object()
        statements = speaker.statements.all()
        serializer = StatementSerializer(statements, many=True)
        return Response(serializer.data)

class StatementViewSet(viewsets.ModelViewSet):
    queryset = Statement.objects.all()
    serializer_class = StatementSerializer

    def get_serializer_class(self):
        if self.action == 'create':
            return StatementCreateSerializer
        return StatementSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            StatementSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
