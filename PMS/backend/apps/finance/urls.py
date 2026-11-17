from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import FinanceSummaryView, FinancialTransactionViewSet, PaymentViewSet, RecurringExpenseViewSet

router = SimpleRouter()
router.register('transactions', FinancialTransactionViewSet, basename='financial-transaction')
router.register('recurring-expenses', RecurringExpenseViewSet, basename='recurring-expense')
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('summary/', FinanceSummaryView.as_view(), name='finance-summary'),
    *router.urls,
]
