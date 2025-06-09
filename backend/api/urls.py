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
    path('sessions/', views.SessionViewSet.as_view({'get': 'list', 'post': 'create'}), name='session-list'),
    path('sessions/<str:pk>/', views.SessionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='session-detail'),
    path('sessions/<str:pk>/bills/', views.SessionViewSet.as_view({'get': 'bills'}), name='session-bills'),
    path('sessions/<str:pk>/statements/', views.SessionViewSet.as_view({'get': 'statements'}), name='session-statements'),
    path('sessions/<str:pk>/sentiment_by_party/', views.session_sentiment_by_party, name='session-sentiment-by-party'),

    path('bills/', views.BillViewSet.as_view({'get': 'list', 'post': 'create'}), name='bill-list'),
    path('bills/<str:pk>/', views.BillViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='bill-detail'),
    path('bills/<str:pk>/statements/', views.BillViewSet.as_view({'get': 'statements'}), name='bill-statements'),
    path('bills/<str:pk>/sentiment/', views.BillViewSet.as_view({'get': 'sentiment'}), name='bill-sentiment'),
    path('bills/<str:pk>/voting-sentiment/', views.BillViewSet.as_view({'get': 'voting_sentiment'}), name='bill-voting-sentiment'),

    path('speakers/', views.SpeakerViewSet.as_view({'get': 'list', 'post': 'create'}), name='speaker-list'),
    path('speakers/<str:pk>/', views.SpeakerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='speaker-detail'),
    path('speakers/<str:pk>/statements/', views.SpeakerViewSet.as_view({'get': 'statements'}), name='speaker-statements'),

    path('statements/', views.statement_list, name='statement-list'),
    path('statements/create/', views.StatementViewSet.as_view({'post': 'create'}), name='statement-create'),

    path('parties/', views.PartyViewSet.as_view({'get': 'list', 'post': 'create'}), name='party-list'),
    path('parties/<int:pk>/', views.PartyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='party-detail'),

    # Data and analytics endpoints
    path('data/refresh/', views.refresh_all_data, name='refresh-all-data'),
    path('data/status/', views.data_status, name='data-status'),

    # Missing endpoints that frontend is calling
    path('home-data/', views.home_data, name='home-data'),
    path('stats/', views.stats_overview, name='stats-overview'),
    path('stats-overview/', views.stats_overview, name='stats-overview-alt'),

    # Analytics endpoints
    path('analytics/sentiment/', views.overall_sentiment_stats, name='overall-sentiment-stats'),
    path('analytics/categories/', views.category_analytics, name='category-analytics'),
    path('analytics/category-sentiment/', views.category_sentiment_analysis, name='category-sentiment-analysis'),
    path('analytics/party-sentiment/', views.sentiment_by_party_and_topic, name='party-sentiment-analysis'),
    path('analytics/parties/', views.party_analytics, name='party-analytics'),
    path('analytics/overall/', views.overall_analytics, name='overall-analytics'),
    path('analytics/categories/<int:category_id>/trends/', views.category_trend_analysis, name='category-trend-analysis'),

    # Utility endpoints
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('trigger-analysis/', views.trigger_statement_analysis, name='trigger-analysis'),
    path('parties-list/', views.parties_list, name='parties-list'),
    path('parties/<int:party_id>/detail/', views.party_detail, name='party-detail-extended'),
    path('sentiment-analysis/', views.sentiment_analysis_list, name='sentiment-analysis-list'),
    path('sessions/<str:session_id>/sentiment-by-party/', views.session_sentiment_by_party, name='session-sentiment-by-party'),

    # Enhanced policy-based sentiment analysis
    path('policy-sentiment-by-category/', views.policy_sentiment_by_category, name='policy_sentiment_by_category'),
    path('speaker/<str:speaker_id>/policy-stance/', views.speaker_policy_stance_analysis, name='speaker_policy_stance'),
    path('party-policy-comparison/', views.party_policy_comparison, name='party_policy_comparison'),
]
```

```replit_final_file
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
    path('sessions/', views.SessionViewSet.as_view({'get': 'list', 'post': 'create'}), name='session-list'),
    path('sessions/<str:pk>/', views.SessionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='session-detail'),
    path('sessions/<str:pk>/bills/', views.SessionViewSet.as_view({'get': 'bills'}), name='session-bills'),
    path('sessions/<str:pk>/statements/', views.SessionViewSet.as_view({'get': 'statements'}), name='session-statements'),
    path('sessions/<str:pk>/sentiment_by_party/', views.session_sentiment_by_party, name='session-sentiment-by-party'),

    path('bills/', views.BillViewSet.as_view({'get': 'list', 'post': 'create'}), name='bill-list'),
    path('bills/<str:pk>/', views.BillViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='bill-detail'),
    path('bills/<str:pk>/statements/', views.BillViewSet.as_view({'get': 'statements'}), name='bill-statements'),
    path('bills/<str:pk>/sentiment/', views.BillViewSet.as_view({'get': 'sentiment'}), name='bill-sentiment'),
    path('bills/<str:pk>/voting-sentiment/', views.BillViewSet.as_view({'get': 'voting_sentiment'}), name='bill-voting-sentiment'),

    path('speakers/', views.SpeakerViewSet.as_view({'get': 'list', 'post': 'create'}), name='speaker-list'),
    path('speakers/<str:pk>/', views.SpeakerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='speaker-detail'),
    path('speakers/<str:pk>/statements/', views.SpeakerViewSet.as_view({'get': 'statements'}), name='speaker-statements'),

    path('statements/', views.statement_list, name='statement-list'),
    path('statements/create/', views.StatementViewSet.as_view({'post': 'create'}), name='statement-create'),

    path('parties/', views.PartyViewSet.as_view({'get': 'list', 'post': 'create'}), name='party-list'),
    path('parties/<int:pk>/', views.PartyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='party-detail'),

    # Data and analytics endpoints
    path('data/refresh/', views.refresh_all_data, name='refresh-all-data'),
    path('data/status/', views.data_status, name='data-status'),

    # Missing endpoints that frontend is calling
    path('home-data/', views.home_data, name='home-data'),
    path('stats/', views.stats_overview, name='stats-overview'),
    path('stats-overview/', views.stats_overview, name='stats-overview-alt'),

    # Analytics endpoints
    path('analytics/sentiment/', views.overall_sentiment_stats, name='overall-sentiment-stats'),
    path('analytics/categories/', views.category_analytics, name='category-analytics'),
    path('analytics/category-sentiment/', views.category_sentiment_analysis, name='category-sentiment-analysis'),
    path('analytics/party-sentiment/', views.sentiment_by_party_and_topic, name='party-sentiment-analysis'),
    path('analytics/parties/', views.party_analytics, name='party-analytics'),
    path('analytics/overall/', views.overall_analytics, name='overall-analytics'),
    path('analytics/categories/<int:category_id>/trends/', views.category_trend_analysis, name='category-trend-analysis'),

    # Utility endpoints
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('trigger-analysis/', views.trigger_statement_analysis, name='trigger-analysis'),
    path('parties-list/', views.parties_list, name='parties-list'),
    path('parties/<int:party_id>/detail/', views.party_detail, name='party-detail-extended'),
    path('sentiment-analysis/', views.sentiment_analysis_list, name='sentiment-analysis-list'),
    path('sessions/<str:session_id>/sentiment-by-party/', views.session_sentiment_by_party, name='session-sentiment-by-party'),

    # Enhanced policy-based sentiment analysis
    path('policy-sentiment-by-category/', views.policy_sentiment_by_category, name='policy_sentiment_by_category'),
    path('speaker/<str:speaker_id>/policy-stance/', views.speaker_policy_stance_analysis, name='speaker_policy_stance'),
    path('party-policy-comparison/', views.party_policy_comparison, name='party_policy_comparison'),
]