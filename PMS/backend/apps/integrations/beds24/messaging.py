"""Beds24 mesaj kanalı: OTA (Airbnb / Booking.com) misafir mesajları /bookings/messages üzerinden.

Gelen mesajlar için webhook yok (booking webhook'u mesajları kapsamıyor) -> 3 dakikalık polling.
Mesaj gövdeleri (kapı kodu vb. içerebilir) asla SyncLog'a yazılmaz.
"""
from django.utils import timezone

from apps.integrations.models import ChannelListing, SyncLog
from apps.messaging.models import Message
from apps.messaging.senders import MessageSender, MessageSendError
from apps.messaging.services import ingest_external
from apps.reservations.models import Reservation

from . import mappers
from .client import Beds24Client, Beds24Error, Beds24TransientError, check_post_results

SOURCE_MAP = {'guest': Message.Source.GUEST, 'host': Message.Source.HOST, 'system': Message.Source.SYSTEM}
POLL_MAX_AGE_DAYS = 2


class Beds24MessageSender(MessageSender):
    channel = 'beds24'

    def __init__(self, client=None):
        self.client = client or Beds24Client()

    def send(self, reservation, subject, body):
        if not reservation.external_source_id:
            raise MessageSendError('Reservation is not linked to a Beds24 booking')
        try:
            results = check_post_results(
                self.client.post('/bookings/messages', [{
                    'bookingId': int(reservation.external_source_id), 'message': body, 'source': 'host',
                }], action='message.send'),
                'message.send',
            )
        except Beds24TransientError:
            raise  # 429/5xx/ağ: planlı mesaj tekrar denenir
        except Beds24Error as exc:
            raise MessageSendError(str(exc)) from exc
        new_id = mappers.new_id_from_post(results)
        # Polling'de aynı mesaj aynı id ile gelir; çift kayıt olmasın diye aynı biçim kullanılır.
        return f'beds24:{new_id}' if new_id else None

    def mark_read(self, external_ids):
        ids = [int(str(i).split(':')[-1]) for i in external_ids if str(i).split(':')[-1].isdigit()]
        if ids:
            self.client.request('PATCH', '/bookings/messages', params={'messageId': ids}, json={'read': True},
                                action='message.read')


def poll_messages(client=None, max_age_days=POLL_MAX_AGE_DAYS):
    """Bağlı evlerin son mesajlarını çekip birleşik mesaj kutusuna idempotent aktarır."""
    client = client or Beds24Client()
    connection = client.connection
    property_ids = list(
        ChannelListing.objects.filter(connection=connection, sync_enabled=True)
        .exclude(external_listing_id='').values_list('external_listing_id', flat=True)
    )
    if not property_ids:
        return {}
    items = client.get_all('/bookings/messages', params={'propertyId': property_ids, 'maxAge': max_age_days},
                           action='message.poll')
    booking_ids = {str(m.get('bookingId')) for m in items if m.get('bookingId')}
    reservations = {
        r.external_source_id: r
        for r in Reservation.objects.filter(external_source_id__in=booking_ids).select_related('property', 'guest')
    }
    summary = {}
    for item in items:
        source = SOURCE_MAP.get(item.get('source'))
        reservation = reservations.get(str(item.get('bookingId')))
        if source is None or reservation is None or not item.get('id'):
            result = 'skipped'
        else:
            _, created = ingest_external(
                reservation,
                external_id=f"beds24:{item['id']}",
                body=item.get('message') or '',
                sent_at=mappers.parse_beds24_datetime(item.get('time')) or timezone.now(),
                source=source,
                is_read=bool(item.get('read')),
            )
            result = 'new' if created else 'known'
        summary[result] = summary.get(result, 0) + 1
    if summary.get('new'):
        SyncLog.objects.create(connection=connection, action='message.poll.summary', status='success',
                               message=f"{summary['new']} yeni mesaj", details=summary)
    return summary
