"""Beds24 Celery task'ları. Geçici hatalarda (429/5xx/ağ) exponential backoff ile tekrar denenir."""
import logging
from datetime import date

from celery import shared_task
from django.core.exceptions import ImproperlyConfigured

from apps.integrations.models import ChannelListing, WebhookEvent
from apps.properties.models import Property
from apps.reservations.models import Reservation

from . import services
from .client import Beds24Error, Beds24TransientError, get_connection

logger = logging.getLogger(__name__)

RETRY = dict(
    autoretry_for=(Beds24TransientError,), retry_backoff=30, retry_backoff_max=900,
    retry_jitter=True, max_retries=6,
)


def _date(value):
    return date.fromisoformat(value) if value else None


@shared_task(**RETRY)
def sync_property_task(property_id):
    prop = Property.objects.filter(pk=property_id).first()
    if prop is None:
        return 'missing'
    try:
        services.sync_property(prop)
    except (Beds24Error, ImproperlyConfigured) as exc:
        if isinstance(exc, Beds24TransientError):
            raise
        logger.warning('Beds24 property sync başarısız: %s', exc)
        return 'error'
    return 'ok'


@shared_task(**RETRY)
def push_rates_task(property_id, date_from=None, date_to=None):
    prop = Property.objects.filter(pk=property_id).first()
    if prop is None:
        return 0
    return services.push_rates(prop, _date(date_from), _date(date_to))


@shared_task(**RETRY)
def push_booking_task(reservation_id):
    reservation = Reservation.objects.select_related('guest', 'property').filter(pk=reservation_id).first()
    if reservation is None:
        return None
    return services.push_booking(reservation)


@shared_task(**RETRY)
def delete_booking_task(booking_id):
    return services.delete_booking(booking_id)


@shared_task(**RETRY)
def process_webhook_event(event_id):
    event = WebhookEvent.objects.filter(pk=event_id).first()
    if event is None:
        return 'missing'
    try:
        return services.process_webhook_event(event)
    except Beds24TransientError:
        raise
    except Exception as exc:
        WebhookEvent.objects.filter(pk=event_id).update(error=f'{exc.__class__.__name__}: {str(exc)[:500]}')
        raise


@shared_task(**RETRY)
def poll_bookings():
    try:
        return services.pull_bookings()
    except ImproperlyConfigured as exc:
        logger.info('Beds24 polling atlandı: %s', exc)
        return {}


@shared_task
def nightly_full_sync():
    """03:00: bağlı tüm evler için 365 günlük tam takvim; hatalı/bekleyen eşlemeler için property sync."""
    connection = get_connection()
    listings = ChannelListing.objects.filter(connection=connection, sync_enabled=True).select_related('property')
    for listing in listings:
        if listing.sync_status != ChannelListing.SyncStatus.OK or not listing.external_room_id:
            sync_property_task.delay(str(listing.property_id))
        else:
            push_rates_task.delay(str(listing.property_id))
    # Hiç eşlenmemiş aktif evler (ör. kuyruk çalışmıyorken oluşturulmuş olanlar).
    linked = listings.values_list('property_id', flat=True)
    for prop_id in Property.objects.filter(is_active=True).exclude(pk__in=linked).values_list('pk', flat=True):
        sync_property_task.delay(str(prop_id))


@shared_task(**RETRY)
def poll_messages():
    from .messaging import poll_messages as _poll

    try:
        return _poll()
    except ImproperlyConfigured as exc:
        logger.info('Beds24 mesaj polling atlandı: %s', exc)
        return {}
