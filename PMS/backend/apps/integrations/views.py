import os
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.properties.models import Property
from apps.properties.pricing import suggested_markup
from .beds24 import services
from .beds24.client import Beds24Error, get_connection
from .models import ChannelListing, SyncLog
from .serializers import ChannelListingSerializer, SyncLogSerializer
from .signals import enqueue



class ChannelOverviewView(APIView):
    """Ev x kanal tablosu: Beds24 eşlemesi, Airbnb/Booking bağlı mı, son senkron, hata."""

    def get(self, request):
        connection = get_connection()
        listings = {
            listing.property_id: listing
            for listing in ChannelListing.objects.filter(connection=connection).select_related('connection')
        }
        rows = []
        for prop in Property.objects.order_by('name', 'id'):
            listing = listings.get(prop.pk)
            rows.append({
                'property': {'id': str(prop.pk), 'name': prop.name, 'city': prop.city, 'is_active': prop.is_active},
                'listing': ChannelListingSerializer(listing).data if listing else None,
            })
        commissions = {k: Decimal(str(settings.CHANNEL_COMMISSIONS[k])) for k in ('airbnb', 'booking')}
        return Response({
            'provider': 'beds24',
            'configured': bool(os.getenv('BEDS24_REFRESH_TOKEN')),
            'webhook_configured': bool(os.getenv('BEDS24_WEBHOOK_SECRET')),
            'webhook_auto_register': bool(services.webhook_url()),
            'last_poll_at': connection.last_synced_at,
            # Beds24 API V2 fotoğraf yüklemeyi desteklemiyor (properties POST'ta resim alanı yok).
            'photos_supported': False,
            # Beds24 API V2 OTA bağlantı durumunu vermiyor; ChannelListing üzerinde elle işaretlenir.
            'channel_status_manual': True,
            'commissions': {k: str(v) for k, v in commissions.items()},
            'suggested_markup': {k: str(suggested_markup(v)) for k, v in commissions.items()},
            'results': rows,
        })


class ChannelListingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Eşleme ayarları: markup yüzdeleri, kanal bağlı işaretleri, senkron açık/kapalı."""
    queryset = ChannelListing.objects.select_related('connection', 'property').order_by('property__name')
    serializer_class = ChannelListingSerializer
    filterset_fields = ['property', 'sync_status']

    def perform_update(self, serializer):
        before = serializer.instance
        old = (before.airbnb_markup_percent, before.booking_markup_percent, before.sync_enabled)
        listing = serializer.save()
        if (listing.airbnb_markup_percent, listing.booking_markup_percent, listing.sync_enabled) != old:
            from .beds24.tasks import push_rates_task

            enqueue(push_rates_task, str(listing.property_id))


class PropertySyncView(APIView):
    """Elle senkron: ev bilgileri + 365 günlük takvim. Sonucu beklemek için senkron çalışır."""

    def post(self, request, pk):
        prop = get_object_or_404(Property, pk=pk)
        try:
            listing = services.sync_property(prop)
        except ImproperlyConfigured as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Beds24Error as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(ChannelListingSerializer(listing).data)


class SyncLogFilter(filters.FilterSet):
    action = filters.CharFilter(lookup_expr='icontains')
    created_from = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_to = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = SyncLog
        fields = ['status', 'action', 'created_from', 'created_to']


class SyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SyncLog.objects.order_by('-created_at')
    serializer_class = SyncLogSerializer
    filterset_class = SyncLogFilter
    search_fields = ['message', 'action']
    ordering_fields = ['created_at']
