"""Beds24 servis katmanı. PMS'in geri kalanı sadece bu fonksiyonları (task'lar üzerinden) çağırır."""
import logging
import os
import uuid
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.guests.models import Guest
from apps.integrations.models import ChannelListing, SyncLog, WebhookEvent
from apps.properties import pricing
from apps.reservations.models import Reservation, ReservationStatusHistory

from . import mappers
from .client import Beds24Client, Beds24Error, check_post_results, get_connection

logger = logging.getLogger(__name__)

# Bu statülerdeki yerel rezervasyonlar kanal güncellemesiyle geri alınmaz (konaklama bitti).
FINAL_LOCAL_STATUSES = {Reservation.Status.COMPLETED, Reservation.Status.NO_SHOW}
DIRECT_LOCAL_FIELDS = (
    'source', 'channel_booking_ref', 'channel_commission', 'commission_is_estimated', 'taxes', 'cleaning_fee',
)
POLL_OVERLAP = timedelta(minutes=5)
FIRST_POLL_WINDOW = timedelta(days=30)


def _client(client):
    return client or Beds24Client()


def get_listing(prop):
    connection = get_connection()
    return ChannelListing.objects.filter(connection=connection, property=prop).first()


def webhook_url():
    secret = os.getenv('BEDS24_WEBHOOK_SECRET')
    if not (settings.PUBLIC_BASE_URL and secret):
        return None
    return settings.PUBLIC_BASE_URL + reverse('beds24-webhook', kwargs={'secret': secret})


def _mark(listing, status, error=''):
    listing.sync_status = status
    listing.last_error = error[:1000]
    if status == ChannelListing.SyncStatus.OK:
        listing.last_synced_at = timezone.now()
    listing.save(update_fields=['sync_status', 'last_error', 'last_synced_at', 'updated_at'])


def sync_window(date_from=None, date_to=None):
    today = timezone.localdate(timezone=pricing.property_tz())
    last = today + timedelta(days=settings.BEDS24_SYNC_DAYS - 1)
    start = max(date_from or today, today)
    end = min(date_to or last, last)
    return start, end


# --------------------------------------------------------------------------- property
def _fetch_room_id(client, property_id):
    data = client.get('/properties', params={'id': property_id, 'includeAllRooms': 'true'},
                      action='property.fetch')
    for prop in (data or {}).get('data') or []:
        rooms = prop.get('roomTypes') or []
        if rooms:
            return str(rooms[0]['id'])
    return None


def sync_property(prop, client=None, push_calendar=True):
    """Evi Beds24'te oluşturur (eşleme yoksa) veya günceller; ardından takvimi gönderir."""
    client = _client(client)
    connection = client.connection
    listing = ChannelListing.objects.filter(connection=connection, property=prop).first()
    try:
        payload = mappers.property_payload(prop, listing, webhook_url())
        results = check_post_results(
            client.post('/properties', [payload], action='property.sync'), 'property.sync',
        )
        if listing is None or not listing.external_listing_id:
            property_id = mappers.new_id_from_post(results)
            if not property_id:
                raise Beds24Error('Beds24 yeni property id döndürmedi')
            listing, _ = ChannelListing.objects.update_or_create(
                connection=connection, property=prop,
                defaults={'external_listing_id': property_id},
            )
        if not listing.external_room_id:
            room_id = _fetch_room_id(client, listing.external_listing_id)
            if not room_id:
                raise Beds24Error('Beds24 property için roomType bulunamadı')
            listing.external_room_id = room_id
            listing.save(update_fields=['external_room_id', 'updated_at'])
        if push_calendar:
            push_rates(prop, client=client, listing=listing)
        _mark(listing, ChannelListing.SyncStatus.OK)
    except Beds24Error as exc:
        if listing is not None:
            _mark(listing, ChannelListing.SyncStatus.ERROR, str(exc))
        raise
    return listing


def link_property(prop, beds24_property_id, client=None):
    """Var olan bir Beds24 property'sini PMS evine bağlar (ev Beds24'te önceden oluşturulmuşsa)."""
    client = _client(client)
    connection = client.connection
    data = client.get('/properties', params={'id': beds24_property_id, 'includeAllRooms': 'true'},
                      action='property.fetch')
    found = [p for p in (data or {}).get('data') or [] if str(p.get('id')) == str(beds24_property_id)]
    if not found:
        raise Beds24Error(f'Beds24 property {beds24_property_id} bulunamadı')
    rooms = found[0].get('roomTypes') or []
    # Odası yoksa boş bırakılır; ilk sync_property qty=1 odayı Beds24'te oluşturur.
    room_id = str(rooms[0]['id']) if rooms else ''
    listing, _ = ChannelListing.objects.update_or_create(
        connection=connection, property=prop,
        defaults={
            'external_listing_id': str(beds24_property_id),
            'external_room_id': room_id,
            'sync_status': ChannelListing.SyncStatus.PENDING,
            'last_error': '',
        },
    )
    return listing


# --------------------------------------------------------------------------- rates
def push_rates(prop, date_from=None, date_to=None, client=None, listing=None):
    """Etkin fiyat, min stay ve kapalı günleri tek istekte Beds24 takvimine yazar."""
    listing = listing or get_listing(prop)
    if listing is None or not listing.external_room_id or not listing.sync_enabled:
        return 0
    start, end = sync_window(date_from, date_to)
    if start > end:
        return 0
    days = pricing.calendar(prop, start, end)
    entries = mappers.calendar_entries(days, listing.airbnb_markup_percent, listing.booking_markup_percent)
    client = _client(client)
    check_post_results(
        client.post('/inventory/rooms/calendar', mappers.calendar_payload(listing.external_room_id, entries),
                    action='rates.push'),
        'rates.push',
    )
    return len(entries)


# --------------------------------------------------------------------------- outbound booking
def push_booking(reservation, client=None):
    """PMS'te oluşturulan (direkt) rezervasyonu Beds24'e yazar; kanallarda tarih kapanır."""
    listing = get_listing(reservation.property)
    if listing is None or not listing.external_room_id or not listing.sync_enabled:
        return None
    if not reservation.external_source_id and reservation.status in ('cancelled', 'no_show'):
        return None  # Beds24'te hiç olmayan bir rezervasyonu iptal olarak göndermeye gerek yok.
    client = _client(client)
    payload = mappers.reservation_to_booking(reservation, listing.external_room_id)
    results = check_post_results(client.post('/bookings', [payload], action='booking.push'), 'booking.push')
    if not reservation.external_source_id:
        booking_id = mappers.new_id_from_post(results)
        if booking_id:
            # .update(): sinyal tetiklenmez, döngü oluşmaz.
            Reservation.objects.filter(pk=reservation.pk).update(
                external_source_id=booking_id, last_synced_at=timezone.now(),
            )
            reservation.external_source_id = booking_id
    else:
        Reservation.objects.filter(pk=reservation.pk).update(last_synced_at=timezone.now())
    return reservation.external_source_id


def delete_booking(booking_id, client=None):
    """PMS'te silinen (PMS'te açılmış) rezervasyonun Beds24 kaydını siler; takvim tekrar açılır."""
    client = _client(client)
    check_post_results(
        client.request('DELETE', '/bookings', params={'id': [int(booking_id)]}, action='booking.delete'),
        'booking.delete',
    )
    return str(booking_id)


# --------------------------------------------------------------------------- inbound bookings
BOOKING_STATUSES_ALL = ['confirmed', 'request', 'new', 'cancelled']
# GET /bookings varsayılan olarak sadece gelecekteki rezervasyonları döndürür; id ile sorguda geçmişi de kapsasın.
# TODO(beds24): doğrula — arrivalFrom'un id sorgusundaki "sadece upcoming" varsayılanını kaldırdığı.
LOOKUP_ARRIVAL_FROM = '2000-01-01'
RECONCILE_CHUNK = 50
ACTIVE_LOCAL_STATUSES = ('pending', 'confirmed')


def fetch_booking(booking_id, client=None):
    client = _client(client)
    data = client.get('/bookings', params={
        'id': booking_id, 'includeInvoiceItems': 'true', 'status': BOOKING_STATUSES_ALL,
        'arrivalFrom': LOOKUP_ARRIVAL_FROM,
    }, action='booking.fetch')
    items = (data or {}).get('data') or []
    return items[0] if items else None


def cancel_missing_booking(reservation, connection):
    """Beds24'te silinmiş rezervasyonu PMS'te iptal eder (geçmiş ve finans tutarlı kalsın diye silinmez)."""
    if reservation.status not in ACTIVE_LOCAL_STATUSES:
        return False
    old_status = reservation.status
    reservation.status = Reservation.Status.CANCELLED
    reservation.last_synced_at = timezone.now()
    reservation._from_channel = True  # Beds24'e geri gönderilmesin (orada artık yok)
    reservation.save(update_fields=['status', 'last_synced_at', 'updated_at'])
    _history(reservation, old_status)
    SyncLog.objects.create(
        connection=connection, action='booking.deleted_in_beds24', status='success',
        message=f'Beds24 #{reservation.external_source_id} Beds24\'te silinmiş: PMS\'te iptal edildi',
        details={'reservation': str(reservation.pk)},
    )
    return True


def reconcile_deleted_bookings(client=None):
    """PMS'teki aktif, Beds24'e bağlı rezervasyonlar Beds24'te hâlâ var mı? Yoksa (silinmişse) PMS'te iptal et.

    Silinen rezervasyonlar 'modifiedFrom' polling'inde hiç görünmez; bu kontrol o boşluğu kapatır.
    Güvenlik: Beds24 hiçbir kaydı döndürmezse (API/izin sorunu olabilir) toplu iptal yapılmaz.
    """
    client = _client(client)
    connection = client.connection
    today = timezone.localdate(timezone=pricing.property_tz())
    candidates = list(
        Reservation.objects.exclude(external_source_id='')
        .filter(status__in=ACTIVE_LOCAL_STATUSES, check_out__date__gte=today)
    )
    if not candidates:
        return 0
    ids = [r.external_source_id for r in candidates]
    found = set()
    for i in range(0, len(ids), RECONCILE_CHUNK):
        chunk = ids[i:i + RECONCILE_CHUNK]
        items = client.get_all('/bookings', params={
            'id': [int(x) for x in chunk if x.isdigit()],
            'status': BOOKING_STATUSES_ALL + ['black', 'inquiry'],
            'arrivalFrom': LOOKUP_ARRIVAL_FROM,
        }, action='booking.reconcile', log=False)
        found |= {str(b.get('id')) for b in items}
    if not found and len(ids) > 1:
        SyncLog.objects.create(
            connection=connection, action='booking.reconcile', status='error',
            message=f'Beds24 {len(ids)} rezervasyonun hiçbirini döndürmedi; güvenlik için iptal yapılmadı',
        )
        return 0
    cancelled = 0
    for reservation in candidates:
        if reservation.external_source_id not in found:
            with transaction.atomic():
                locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
                cancelled += int(cancel_missing_booking(locked, connection))
    return cancelled


def _find_guest(fields):
    email = fields['email']
    if email:
        guest = Guest.objects.filter(email__iexact=email).order_by('created_at').first()
        if guest:
            return guest
    phone = fields['phone']
    if phone:
        guest = Guest.objects.filter(phone=phone).order_by('created_at').first()
        if guest:
            return guest
    return Guest.objects.create(**fields)


def _history(reservation, old_status):
    ReservationStatusHistory.objects.create(
        reservation=reservation, old_status=old_status, new_status=reservation.status,
    )


def _find_local_by_api_reference(booking):
    """PMS'ten gönderilen rezervasyonlar Beds24'e apiReference=<reservation uuid> ile gider."""
    ref = booking.get('apiReference') or ''
    try:
        pk = uuid.UUID(str(ref))
    except ValueError:
        return None
    return Reservation.objects.select_for_update().filter(pk=pk).first()


def upsert_booking(booking, connection=None):
    """Beds24 booking'i idempotent olarak Reservation'a yazar.

    Dönüş: (reservation | None, 'created' | 'updated' | 'unchanged' | 'skipped:<neden>')
    """
    connection = connection or get_connection()
    listing = (
        ChannelListing.objects.select_related('property')
        .filter(connection=connection, external_listing_id=str(booking.get('propertyId')))
        .first()
    )
    if listing is None:
        return None, 'skipped:unlinked_property'

    status = mappers.map_status(booking.get('status'), booking.get('subStatus'))
    fields = mappers.reservation_fields(booking)
    external_id = fields['external_source_id']

    for attempt in range(2):
        try:
            with transaction.atomic():
                reservation = (
                    Reservation.objects.select_for_update().filter(external_source_id=external_id).first()
                    or _find_local_by_api_reference(booking)
                )
                if reservation is None:
                    if status in (None, 'cancelled', 'no_show'):
                        return None, f'skipped:{booking.get("status")}'
                    reservation = Reservation(
                        property=listing.property,
                        guest=_find_guest(mappers.guest_fields(booking)),
                        status=status,
                        last_synced_at=timezone.now(),
                        created_via_channel=True,
                        **fields,
                    )
                    reservation._from_channel = True
                    reservation.save()
                    _history(reservation, '')
                    _warn_overlap(reservation)
                    return reservation, 'created'
                return _apply_update(reservation, listing, status, fields)
        except IntegrityError:
            # Aynı booking eşzamanlı iki kez işlendi: ikinci denemede güncelleme olarak devam et.
            if attempt:
                raise
    return None, 'skipped:conflict'


def _apply_update(reservation, listing, status, fields):
    old_status = reservation.status
    if not reservation.created_via_channel and not reservation.external_source_id:
        # PMS'te oluşturulmuş, Beds24'e gitmiş rezervasyon geri geldi: sadece eşlemeyi tamamla.
        fields = {'external_source_id': fields['external_source_id']}
    elif not reservation.created_via_channel:
        # PMS'te açılan rezervasyonda (kaynağı Airbnb seçilmiş olsa bile) kaynak, onay kodu ve
        # finans bilgisi PMS'te otoriterdir.
        fields = {k: v for k, v in fields.items() if k not in DIRECT_LOCAL_FIELDS}
    elif fields.get('channel_commission') is None:
        # Kanal komisyon bildirmiyor: mevcut (tahmini veya elle girilmiş) komisyona dokunma.
        fields = {k: v for k, v in fields.items() if k not in ('channel_commission', 'commission_is_estimated')}

    changed = []
    for name, value in fields.items():
        if getattr(reservation, name) != value:
            setattr(reservation, name, value)
            changed.append(name)
    if reservation.property_id != listing.property_id:
        reservation.property = listing.property
        changed.append('property')
    if status and status != reservation.status and reservation.status not in FINAL_LOCAL_STATUSES:
        reservation.status = status
        changed.append('status')
    reservation.last_synced_at = timezone.now()
    reservation._from_channel = True
    reservation.save(update_fields=[*changed, 'last_synced_at', 'updated_at'])
    if reservation.status != old_status:
        _history(reservation, old_status)
    if not changed:
        return reservation, 'unchanged'
    if {'check_in', 'check_out', 'property', 'status'} & set(changed):
        _warn_overlap(reservation)
    return reservation, 'updated'


def _warn_overlap(reservation):
    """Kanal verisi otoriter: çakışma olsa da kaydedilir, ama loglanır."""
    from apps.reservations.serializers import BLOCKING_STATUSES

    if reservation.status not in BLOCKING_STATUSES:
        return
    clash = Reservation.objects.filter(
        property=reservation.property, status__in=BLOCKING_STATUSES,
        check_in__lt=reservation.check_out, check_out__gt=reservation.check_in,
    ).exclude(pk=reservation.pk).exists()
    if clash:
        SyncLog.objects.create(
            connection=get_connection(), action='booking.overlap', status='error',
            message=f'Çakışan rezervasyon: {reservation.property.name} / Beds24 #{reservation.external_source_id}',
            details={'reservation': str(reservation.pk)},
        )


def import_booking(booking_id, client=None):
    """Booking'i Beds24'ten otoriter olarak çekip upsert eder (webhook gövdesine güvenilmez)."""
    client = _client(client)
    booking = fetch_booking(booking_id, client=client)
    if booking is None:
        # Beds24'te silinmiş: PMS'te karşılığı varsa iptal et.
        reservation = Reservation.objects.filter(external_source_id=str(booking_id)).first()
        if reservation is not None and cancel_missing_booking(reservation, client.connection):
            return reservation, 'cancelled:deleted_in_beds24'
        return None, 'skipped:not_found'
    return upsert_booking(booking, client.connection)


def pull_bookings(client=None, modified_from=None):
    """Son başarılı polling'den beri değişen rezervasyonları çeker (webhook kaçarsa yedek)."""
    client = _client(client)
    connection = client.connection
    property_ids = list(
        ChannelListing.objects.filter(connection=connection, sync_enabled=True)
        .exclude(external_listing_id='').values_list('external_listing_id', flat=True)
    )
    if not property_ids:
        return {}
    started = timezone.now()
    since = modified_from or (
        connection.last_synced_at - POLL_OVERLAP if connection.last_synced_at else started - FIRST_POLL_WINDOW
    )
    bookings = client.get_all('/bookings', params={
        'propertyId': property_ids,
        'modifiedFrom': since.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
        'status': BOOKING_STATUSES_ALL,
        'includeInvoiceItems': 'true',
    }, action='booking.poll')
    summary = {}
    for booking in bookings:
        try:
            _, result = upsert_booking(booking, connection)
        except Exception as exc:  # Tek bir bozuk kayıt tüm polling'i durdurmasın.
            logger.exception('Beds24 booking işlenemedi')
            result = 'error'
            SyncLog.objects.create(
                connection=connection, action='booking.upsert', status='error',
                message=f'Beds24 #{booking.get("id")}: {exc.__class__.__name__}: {str(exc)[:200]}',
            )
        summary[result] = summary.get(result, 0) + 1
    deleted = reconcile_deleted_bookings(client)
    if deleted:
        summary['cancelled:deleted_in_beds24'] = deleted
    connection.last_synced_at = started
    connection.save(update_fields=['last_synced_at', 'updated_at'])
    SyncLog.objects.create(
        connection=connection, action='booking.poll.summary', status='success',
        message=f'{len(bookings)} rezervasyon işlendi', details=summary,
    )
    return summary


def process_webhook_event(event):
    """Kaydedilmiş WebhookEvent'i işler: booking id ile Beds24'ten tekrar çekip upsert eder."""
    if event.processed:
        return 'already_processed'
    booking_id = ((event.payload or {}).get('booking') or {}).get('id')
    if not booking_id:
        result = 'skipped:no_booking_id'
    else:
        _, result = import_booking(booking_id)
    WebhookEvent.objects.filter(pk=event.pk).update(
        processed=True, processed_at=timezone.now(), error='',
    )
    return result
