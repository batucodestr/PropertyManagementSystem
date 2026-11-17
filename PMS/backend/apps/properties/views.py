from datetime import date, timedelta

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.views import ProtectedDeleteMixin
from . import pricing
from .models import DailyRate, Property, PropertyImage, SeasonalRate
from .serializers import (
    BulkDailyRateSerializer, DailyRateSerializer, PropertyImageSerializer, PropertySerializer,
    SeasonalRateSerializer,
)
from .signals import rates_changed

MAX_CALENDAR_DAYS = 400


def _parse_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({name: 'Use the YYYY-MM-DD format.'})


class PropertyViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Property.objects.prefetch_related('images').order_by('name', 'id')
    serializer_class = PropertySerializer
    filterset_fields = ['is_active', 'city', 'country', 'max_guests', 'bedroom_count']
    search_fields = ['name', 'city', 'address', 'country']
    ordering_fields = ['name', 'base_price', 'max_guests', 'city']

    @action(detail=True, methods=['get'], url_path='rates')
    def rates(self, request, pk=None):
        """Gün gün etkin fiyat, kaynağı, min stay ve müsaitlik. ?from=YYYY-MM-DD&to=YYYY-MM-DD (dahil)."""
        prop = self.get_object()
        params = request.query_params
        start = _parse_date(params['from'], 'from') if params.get('from') else date.today()
        end = _parse_date(params['to'], 'to') if params.get('to') else start + timedelta(days=30)
        if end < start:
            raise ValidationError({'to': 'End date cannot be before start date.'})
        if (end - start).days >= MAX_CALENDAR_DAYS:
            raise ValidationError({'to': f'The range can be at most {MAX_CALENDAR_DAYS} days.'})
        days = pricing.calendar(prop, start, end)
        return Response({
            'property': str(prop.pk),
            'base_price': str(prop.base_price),
            'from': start.isoformat(),
            'to': end.isoformat(),
            'days': [d.as_dict() for d in days],
        })

    @action(detail=True, methods=['post'], url_path='rates/bulk')
    def rates_bulk(self, request, pk=None):
        """Aralığa gün override'ı uygular (veya clear=true ile siler); kanallara tek push gider."""
        prop = self.get_object()
        serializer = BulkDailyRateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        start, end = data['date_from'], data['date_to']
        with transaction.atomic():
            if data['clear']:
                DailyRate.objects.filter(property=prop, date__range=(start, end)).delete()
            else:
                existing = {r.date: r for r in DailyRate.objects.filter(property=prop, date__range=(start, end))}
                for day in pricing.daterange(start, end):
                    rate = existing.get(day) or DailyRate(property=prop, date=day)
                    if 'price' in data:
                        rate.price = data['price']
                    if 'min_stay' in data:
                        rate.min_stay = data['min_stay']
                    rate.closed = data['closed']
                    rate._skip_push = True
                    rate.save()
            rates_changed.send(sender=Property, property=prop, date_from=start, date_to=end)
        return Response({'updated': (end - start).days + 1}, status=status.HTTP_200_OK)


class PropertyImageViewSet(viewsets.ModelViewSet):
    queryset = PropertyImage.objects.select_related('property').order_by('id')
    serializer_class = PropertyImageSerializer
    filterset_fields = ['property']


class SeasonalRateViewSet(viewsets.ModelViewSet):
    queryset = SeasonalRate.objects.select_related('property').order_by('start_date', 'id')
    serializer_class = SeasonalRateSerializer
    filterset_fields = {
        'property': ['exact'],
        'start_date': ['gte', 'lte'],
        'end_date': ['gte', 'lte'],
    }


class DailyRateViewSet(viewsets.ModelViewSet):
    queryset = DailyRate.objects.select_related('property').order_by('date')
    serializer_class = DailyRateSerializer
    filterset_fields = {
        'property': ['exact'],
        'date': ['exact', 'gte', 'lte'],
        'closed': ['exact'],
    }
