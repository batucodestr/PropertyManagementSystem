from django.urls import path
from rest_framework.routers import SimpleRouter

from .beds24.webhooks import Beds24WebhookView
from .views import ChannelListingViewSet, ChannelOverviewView, PropertySyncView, SyncLogViewSet

router = SimpleRouter()
router.register('listings', ChannelListingViewSet, basename='channel-listing')
router.register('sync-logs', SyncLogViewSet, basename='sync-log')

urlpatterns = [
    path('channels/', ChannelOverviewView.as_view(), name='channel-overview'),
    path('properties/<uuid:pk>/sync/', PropertySyncView.as_view(), name='property-sync'),
    path('beds24/webhook/<str:secret>/', Beds24WebhookView.as_view(), name='beds24-webhook'),
    *router.urls,
]
