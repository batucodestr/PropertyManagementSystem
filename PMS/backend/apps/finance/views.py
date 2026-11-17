from datetime import date

from django.db.models import Sum
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.views import ProtectedDeleteMixin
from apps.properties.models import Property
from apps.reservations.models import Reservation
from . import reports
from .models import FinancialTransaction, RecurringExpense
from .serializers import FinancialTransactionSerializer, PaymentSerializer, RecurringExpenseSerializer
from .services import INCOME_STATUSES

MAX_SUMMARY_DAYS = 731


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Use the YYYY-MM-DD format.'})


class FinanceSummaryView(APIView):
    """GET /api/finance/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD&property=<uuid> (varsayılan: bu ay)."""

    def get(self, request):
        params = request.query_params
        start, end = reports.default_range()
        if params.get('from'):
            start = _parse_date(params['from'], 'from')
        if params.get('to'):
            end = _parse_date(params['to'], 'to')
        if end < start:
            raise ValidationError({'to': 'End date cannot be before start date.'})
        if (end - start).days > MAX_SUMMARY_DAYS:
            raise ValidationError({'to': 'The range can be at most two years.'})
        property_id = params.get('property') or None
        if property_id and not Property.objects.filter(pk=property_id).exists():
            raise ValidationError({'property': 'Unknown property.'})
        return Response(reports.summary(start, end, property_id))


class FinancialTransactionViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = FinancialTransaction.objects.select_related('property').order_by('-transaction_date', '-created_at')
    serializer_class = FinancialTransactionSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # fiş/fatura yükleme
    filterset_fields = {
        'transaction_type': ['exact'],
        'category': ['exact'],
        'property': ['exact'],
        'reservation': ['exact'],
        'transaction_date': ['gte', 'lte'],
    }
    search_fields = ['description', 'property__name']
    ordering_fields = ['transaction_date', 'amount', 'created_at']

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        total = self.filter_queryset(self.get_queryset()).aggregate(s=Sum('amount'))['s'] or 0
        response.data['total'] = str(total)
        return response

    def perform_destroy(self, instance):
        if FinancialTransactionSerializer().get_is_automatic(instance):
            raise ValidationError('This transaction is managed automatically (reservation / task).')
        instance.delete()


class RecurringExpenseViewSet(viewsets.ModelViewSet):
    queryset = RecurringExpense.objects.select_related('property').order_by('property__name', 'day_of_month')
    serializer_class = RecurringExpenseSerializer
    filterset_fields = ['property', 'category', 'is_active']


class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Gelir getiren rezervasyonların finans/payout listesi."""
    queryset = (
        Reservation.objects.filter(status__in=INCOME_STATUSES)
        .select_related('property', 'guest').order_by('-check_in', 'id')
    )
    serializer_class = PaymentSerializer
    filterset_fields = {
        'property': ['exact'],
        'source': ['exact'],
        'payout_status': ['exact'],
        'commission_is_estimated': ['exact'],
        'check_in': ['gte', 'lte'],
    }
    search_fields = ['guest__first_name', 'guest__last_name', 'property__name', 'channel_booking_ref']
    ordering_fields = ['check_in', 'total_price', 'net_amount', 'payout_date']

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        qs = self.filter_queryset(self.get_queryset())
        totals = {'gross': 0, 'commission': 0, 'net': 0, 'pending_net': 0}
        for total_price, commission, net, payout in qs.values_list(
            'total_price', 'channel_commission', 'net_amount', 'payout_status'
        ):
            totals['gross'] += total_price
            totals['commission'] += commission or 0
            totals['net'] += net
            if payout == Reservation.PayoutStatus.PENDING:
                totals['pending_net'] += net
        response.data['totals'] = {k: str(v) for k, v in totals.items()}
        return response
