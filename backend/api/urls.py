from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'sessions', views.SessionViewSet)
router.register(r'bills', views.BillViewSet)
router.register(r'speakers', views.SpeakerViewSet)
router.register(r'statements', views.StatementViewSet)
router.register(r'parties', views.PartyViewSet)

urlpatterns = [
    # API endpoints
    path('sessions/', views.SessionViewSet.as_view({'get': 'list'}), name='session-list'),
    path('sessions/<str:pk>/', views.SessionViewSet.as_view({'get': 'retrieve'}), name='session-detail'),
    path('sessions/<str:pk>/bills/', views.SessionViewSet.as_view({'get': 'bills'}), name='session-bills'),
    path('sessions/<str:pk>/statements/', views.SessionViewSet.as_view({'get': 'statements'}), name='session-statements'),

    path('bills/', views.BillViewSet.as_view({'get': 'list'}), name='bill-list'),
    path('bills/<str:pk>/', views.BillViewSet.as_view({'get': 'retrieve'}), name='bill-detail'),
    path('bills/<str:pk>/statements/', views.BillViewSet.as_view({'get': 'statements'}), name='bill-statements'),
    path('bills/<str:pk>/sentiment/', views.BillViewSet.as_view({'get': 'sentiment'}), name='bill-sentiment'),
    path('bills/<str:pk>/voting-sentiment/', views.BillViewSet.as_view({'get': 'voting_sentiment'}), name='bill-voting-sentiment'),

    path('speakers/', views.SpeakerViewSet.as_view({'get': 'list'}), name='speaker-list'),
    path('speakers/<str:pk>/', views.SpeakerViewSet.as_view({'get': 'retrieve'}), name='speaker-detail'),
    path('speakers/<str:pk>/statements/', views.SpeakerViewSet.as_view({'get': 'statements'}), name='speaker-statements'),

    path('statements/', views.StatementViewSet.as_view({'get': 'list', 'post': 'create'}), name='statement-list'),
    path('statements/<int:pk>/', views.StatementViewSet.as_view({'get': 'retrieve'}), name='statement-detail'),

    path('parties/', views.PartyViewSet.as_view({'get': 'list'}), name='party-list'),
    path('parties/<int:pk>/', views.PartyViewSet.as_view({'get': 'retrieve'}), name='party-detail'),

    # Alternative list endpoints
    path('statement-list/', views.statement_list, name='statement_list'),
    path('bill-list/', views.bill_list, name='bill_list'),

    # Analytics endpoints
    path('analytics/overall/', views.overall_analytics, name='overall_analytics'),
    path('analytics/parties/', views.party_analytics, name='party_analytics'),
    path('analytics/sentiment/', views.overall_sentiment_stats, name='sentiment_stats'),
    path('analytics/sentiment-by-party/', views.sentiment_by_party_and_topic, name='sentiment_by_party'),
    path('analytics/categories/', views.category_analytics, name='category_analytics'),
    path('analytics/categories/<int:category_id>/trends/', views.category_trend_analysis, name='category_trends'),
    path('analytics/category-sentiment/', views.category_sentiment_analysis, name='category_sentiment'),
    path('sentiment-analysis/', views.sentiment_analysis_list, name='sentiment_analysis_list'),

    # Categories
    path('categories/', views.CategoryListView.as_view(), name='category-list'),

    # Data management endpoints
    path('refresh-data/', views.refresh_all_data, name='refresh_data'),
    path('data-status/', views.data_status, name='data_status'),
    path('trigger-analysis/', views.trigger_statement_analysis, name='trigger_analysis'),

    # Statistics endpoints
    path('stats-overview/', views.stats_overview, name='stats_overview'),
    path('home-data/', views.home_data, name='home_data'),

    # Alternative endpoints for compatibility
    path('parties-list/', views.parties_list, name='parties_list'),
    path('party-detail/<int:party_id>/', views.party_detail, name='party_detail'),
]