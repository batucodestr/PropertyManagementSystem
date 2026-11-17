"""Beds24 booking webhook'u: POST /api/integrations/beds24/webhook/<secret>/

- Secret sabit zamanlı karşılaştırılır; yanlışsa veya tanımlı değilse 404.
- Kimlik doğrulama/CSRF yok, throttling var.
- İstek önce WebhookEvent olarak kaydedilir, hemen 200 dönülür; işleme Celery'de yapılır.
- Gövdenin sadece kişisel veri içermeyen kısmı saklanır; otoriter veri GET /bookings ile çekilir.
"""
import hmac
import logging
import os

from django.http import Http404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.integrations.models import WebhookEvent

logger = logging.getLogger(__name__)

SAFE_BOOKING_KEYS = ('id', 'propertyId', 'roomId', 'status', 'subStatus', 'arrival', 'departure', 'masterId')


def sanitize_payload(data):
    if not isinstance(data, dict):
        return {}
    booking = data.get('booking') if isinstance(data.get('booking'), dict) else {}
    return {
        'timeStamp': data.get('timeStamp'),
        'booking': {k: booking.get(k) for k in SAFE_BOOKING_KEYS if k in booking},
    }


class Beds24WebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'webhook'

    def post(self, request, secret):
        expected = os.getenv('BEDS24_WEBHOOK_SECRET') or ''
        if not expected or not hmac.compare_digest(secret.encode(), expected.encode()):
            raise Http404
        event = WebhookEvent.objects.create(
            provider='beds24', event_type='booking', payload=sanitize_payload(request.data),
        )
        try:
            from .tasks import process_webhook_event

            process_webhook_event.delay(str(event.pk))
        except Exception as exc:  # Kuyruk yoksa polling telafi eder; Beds24'e yine 200 dön.
            logger.warning('Webhook task kuyruğa atılamadı: %s', exc.__class__.__name__)
        return Response({'ok': True})
