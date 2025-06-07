
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Count, Avg
from .views import (
    SessionViewSet, BillViewSet, SpeakerViewSet, StatementViewSet, PartyViewSet,
    CategoryListView,
    category_analytics, category_trend_analysis, trigger_statement_analysis,
    overall_sentiment_stats, statement_list, bill_list,
    refresh_all_data, data_status, parties_list, party_detail,
    category_sentiment_analysis
)
from .models import Session, Bill, Speaker, Statement

@api_view(['GET'])
def stats_view(request):
    """Return general statistics for the dashboard"""
    try:
        total_sessions = Session.objects.count()
        total_bills = Bill.objects.count()
        total_speakers = Speaker.objects.count()
        total_statements = Statement.objects.count()
        avg_sentiment = Statement.objects.aggregate(Avg('sentiment_score'))['sentiment_score__avg'] or 0

        return Response({
            'total_sessions': total_sessions,
            'total_bills': total_bills,
            'total_speakers': total_speakers,
            'total_statements': total_statements,
            'avg_sentiment': round(avg_sentiment, 2)
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)

router = DefaultRouter()
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'bills', BillViewSet, basename='bill')
router.register(r'speakers', SpeakerViewSet, basename='speaker')
router.register(r'statements', StatementViewSet, basename='statement')
router.register(r'parties', PartyViewSet, basename='party')

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', stats_view, name='stats'),

    # Category and analytics endpoints
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('analytics/categories/', category_analytics, name='category-analytics'),
    path('analytics/categories/<int:category_id>/trends/', category_trend_analysis, name='category-trends'),
    path('analytics/category-sentiment/', category_sentiment_analysis, name='category-sentiment'),
    path('analysis/trigger/', trigger_statement_analysis, name='trigger-analysis'),

    # Sentiment analysis endpoints
    path('bills/<str:bill_id>/sentiment/', 'views.BillViewSet', name='bill-sentiment'),
    path('analytics/sentiment/', overall_sentiment_stats, name='overall-sentiment'),

    # List endpoints with filtering
    path('statements/', statement_list, name='statement-list'),
    path('bills/', bill_list, name='bill-list'),

    # Data management endpoints
    path('data/refresh/', refresh_all_data, name='refresh-data'),
    path('data/status/', data_status, name='data-status'),
    path('parties/', parties_list, name='party-list'),
    path('parties/<int:party_id>/', party_detail, name='party-detail'),
]
