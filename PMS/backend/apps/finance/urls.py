from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import FinanceSummaryView, PaymentViewSet

router = SimpleRouter()
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('summary/', FinanceSummaryView.as_view(), name='finance-summary'),
    *router.urls,
]
