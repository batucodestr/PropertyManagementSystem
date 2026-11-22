"""Tanıtım sitesi (Evlerim sayfası) için salt-okunur uç noktalar.

Erişim, PUBLIC_API_KEY ile korunur: `Authorization: Token <anahtar>` veya
`X-Api-Key: <anahtar>` başlığı gerekir. Anahtar tanımlı değilse uç kapalıdır.
Yalnızca aktif mülkler ve PublicPropertySerializer'daki güvenli alanlar döner.
Yazma işlemleri (POST/PUT/PATCH/DELETE) bu uçlarda yoktur.
"""
import hmac

from django.conf import settings
from django.db.models import Prefetch
from rest_framework import mixins, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.throttling import ScopedRateThrottle

from .models import Property, PropertyImage
from .serializers import PublicPropertySerializer


class HasPublicApiKey(BasePermission):
    message = 'Geçerli bir API anahtarı gerekli.'

    def has_permission(self, request, view):
        expected = getattr(settings, 'PUBLIC_API_KEY', '')
        if not expected:
            return False
        header = request.META.get('HTTP_AUTHORIZATION', '')
        scheme, _, value = header.partition(' ')
        provided = value.strip() if scheme.lower() == 'token' else request.META.get('HTTP_X_API_KEY', '')
        return hmac.compare_digest(provided.encode(), expected.encode())


class PublicPropertyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PublicPropertySerializer
    permission_classes = [HasPublicApiKey]
    # JWT çözümlemesi yok: anahtar yalnızca HasPublicApiKey ile doğrulanır.
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public'
    filterset_fields = ['city', 'country', 'bedroom_count', 'max_guests']
    search_fields = ['name', 'city', 'country', 'description']
    ordering_fields = ['name', 'base_price', 'max_guests', 'bedroom_count', 'created_at']

    def get_queryset(self):
        return (
            Property.objects.filter(is_active=True)
            .prefetch_related(Prefetch('images', queryset=PropertyImage.objects.order_by('id')))
            .order_by('-created_at', 'id')
        )
