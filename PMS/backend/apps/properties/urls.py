from rest_framework.routers import SimpleRouter

from .public_views import PublicPropertyViewSet
from .views import DailyRateViewSet, PropertyImageViewSet, PropertyViewSet, SeasonalRateViewSet

router = SimpleRouter()
router.register('properties', PropertyViewSet, basename='property')
router.register('property-images', PropertyImageViewSet, basename='property-image')
router.register('seasonal-rates', SeasonalRateViewSet, basename='seasonal-rate')
router.register('daily-rates', DailyRateViewSet, basename='daily-rate')
# Tanıtım sitesi için herkese açık, salt-okunur liste/detay.
router.register('public/properties', PublicPropertyViewSet, basename='public-property')

urlpatterns = router.urls
