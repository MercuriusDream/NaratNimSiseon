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
    path('', include(router.urls)),
    path('statements/', views.statement_list, name='statement-list'),
    path('bills/', views.bill_list, name='bill-list'),
    path('refresh-data/', views.refresh_all_data, name='refresh-all-data'),
    path('data-status/', views.data_status, name='data-status'),
    path('stats/', views.stats_overview, name='stats-overview'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('analytics/categories/', views.category_analytics, name='category-analytics'),
    path('analytics/categories/<int:category_id>/trends/', views.category_trend_analysis, name='category-trend-analysis'),
    path('analytics/sentiment/overall/', views.overall_sentiment_stats, name='overall-sentiment-stats'),
    path('analytics/overall-sentiment/', views.overall_sentiment_stats, name='overall-sentiment-stats-alt'),
    path('analytics/sentiment/by-party-topic/', views.sentiment_by_party_and_topic, name='sentiment-by-party-topic'),
    path('analytics/sentiment/categories/', views.category_sentiment_analysis, name='category-sentiment-analysis'),
    path('analytics/parties/', views.party_analytics, name='party-analytics'),
    path('analytics/overall/', views.overall_analytics, name='overall-analytics'),
    path('sentiment/', views.sentiment_analysis_list, name='sentiment-analysis-list'),
    path('trigger-analysis/', views.trigger_statement_analysis, name='trigger-analysis'),
    path('home/', views.home_data, name='home-data'),
]