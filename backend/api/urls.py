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
    # Include router URLs
    path('', include(router.urls)),

    # Critical endpoints that frontend needs - MUST BE FIRST
    path('home-data/', views.home_data, name='home-data'),
    path('stats-overview/', views.stats_overview, name='stats-overview'),

    # Data and analytics endpoints
    path('data/refresh/', views.refresh_all_data, name='refresh-all-data'),
    path('data/status/', views.data_status, name='data-status'),

    # Additional view endpoints
    path('statements/', views.statement_list, name='statement-list'),
    path('bills/', views.bill_list, name='bill-list-func'),

    # Session-specific endpoints
    path('sessions/<str:pk>/sentiment_by_party/',
         views.session_sentiment_by_party,
         name='session-sentiment-by-party'),

    # Analytics endpoints
    path('analytics/sentiment/',
         views.sentiment_analysis_list,
         name='overall-sentiment-stats'),
    path('analytics/categories/',
         views.category_analytics,
         name='category-analytics'),
    path('analytics/category-sentiment/',
         views.category_sentiment_analysis,
         name='category-sentiment-analysis'),
    path('analytics/party-sentiment/',
         views.sentiment_by_party_and_topic,
         name='party-sentiment-analysis'),
    path('analytics/parties/', views.party_analytics, name='party-analytics'),
    path('analytics/overall/',
         views.overall_analytics,
         name='overall-analytics'),
    path('analytics/categories/<int:category_id>/trends/',
         views.category_trend_analysis,
         name='category-trend-analysis'),
    path('stats/', views.stats_overview, name='stats-overview'),

    # Utility endpoints
    path('categories/', views.CategoryListView.as_view(),
         name='category-list'),
    path('trigger-analysis/',
         views.trigger_statement_analysis,
         name='trigger-analysis'),
    path('parties-list/', views.parties_list, name='parties-list'),
    path('parties/<int:party_id>/detail/',
         views.party_detail,
         name='party-detail-extended'),
    path('sentiment-analysis/',
         views.sentiment_analysis_list,
         name='sentiment-analysis-list'),

    # Enhanced policy-based sentiment analysis
    path('policy-sentiment-by-category/',
         views.policy_sentiment_by_category,
         name='policy_sentiment_by_category'),
    path('speaker/<str:speaker_id>/policy-stance/',
         views.speaker_policy_stance_analysis,
         name='speaker_policy_stance'),
    path('party-policy-comparison/',
         views.party_policy_comparison,
         name='party_policy_comparison'),

    # Management endpoints
    path('management/force-collection/', views.trigger_force_collection, name='trigger_force_collection'),
    path('management/check-status/', views.check_data_status, name='check_data_status'),
    # Management commands via API
    path('start-collection/', views.start_collection, name='start_collection'),
    path('check-data-status/', views.check_data_status, name='check_data_status'),
]