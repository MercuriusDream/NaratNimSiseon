from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'sessions', views.SessionViewSet)
router.register(r'bills', views.BillViewSet)
router.register(r'speakers', views.SpeakerViewSet)
router.register(r'statements', views.StatementViewSet)
router.register(r'parties', views.PartyViewSet)

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),

    # Additional custom endpoints
    path('stats/', views.data_status, name='stats'),
    path('data-status/', views.data_status, name='data-status'),
    path('refresh-data/', views.refresh_all_data, name='refresh-data'),
    path('statements/', views.statement_list, name='statement-list'),
    path('bills-list/', views.bill_list, name='bill-list'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('category-analytics/', views.category_analytics, name='category-analytics'),
    path('category-trend/<int:category_id>/', views.category_trend_analysis, name='category-trend'),
    path('sentiment-stats/', views.overall_sentiment_stats, name='sentiment-stats'),
    path('category-sentiment/', views.category_sentiment_analysis, name='category-sentiment'),
    path('trigger-analysis/', views.trigger_statement_analysis, name='trigger-analysis'),
    path('parties-list/', views.parties_list, name='parties-list'),
    path('party-detail/<int:party_id>/', views.party_detail, name='party-detail'),
    path('analytics/category-sentiment/', views.category_sentiment_analysis, name='category-sentiment-analysis'),
    path('analytics/overall-sentiment/', views.overall_sentiment_stats, name='overall-sentiment-stats'),
    path('analytics/sentiment/', views.overall_sentiment_stats, name='overall-sentiment-stats'),
    path('analytics/sentiment-by-party-topic/', views.sentiment_by_party_and_topic, name='sentiment-by-party-topic'),
]