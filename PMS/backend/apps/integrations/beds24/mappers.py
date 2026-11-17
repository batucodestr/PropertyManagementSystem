"""PMS modelleri <-> Beds24 JSON dönüşümleri. Saf fonksiyonlar: DB veya ağ erişimi yok.

Alan adları apps/integrations/beds24/openapi.json'dan (Beds24 API V2) alınmıştır.
"""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.properties.pricing import apply_markup, money

# Kanal başına fiyat alanı. Beds24 panelinde Airbnb -> "Price 2", Booking.com -> "Price 3" eşlenmeli.
# price1 = baz fiyat (direkt / Beds24 rezervasyon sayfası).
PRICE_SLOT_BASE = 'price1'
PRICE_SLOT_AIRBNB = 'price2'
PRICE_SLOT_BOOKING = 'price3'

# Beds24 booking.status -> PMS Reservation.status. None: içe aktarılmaz.
# 'new' Beds24'te okunmamış ama geçerli (müsaitliği düşen) rezervasyondur.
STATUS_FROM_BEDS24 = {
    'confirmed': 'confirmed',
    'new': 'confirmed',
    'request': 'pending',
    'cancelled': 'cancelled',
    'inquiry': None,  # soru/talep, rezervasyon değil
    'black': None,    # Beds24'te elle kapatma; PMS'te rezervasyon değil
}

STATUS_TO_BEDS24 = {
    'pending': 'request',
    'confirmed': 'confirmed',
    'completed': 'confirmed',
    'cancelled': 'cancelled',
    'no_show': 'cancelled',
}

AIRBNB_CHANNELS = {'airbnb', 'airbnbical'}
BOOKING_CHANNELS = {'booking'}
# Beds24'te kanal boşsa: kendi rezervasyon sayfası, elle girilen veya API'den gelen rezervasyon.
DIRECT_CHANNELS = {'', 'direct', 'bookingpage'}


def _parse_time(value):
    hour, minute = value.split(':')
    return time(int(hour), int(minute))


def local_datetime(day, hhmm):
    """Beds24'ün tarih-only alanını PROPERTY_TIMEZONE'da yerel saatle aware datetime'a çevirir."""
    tz = ZoneInfo(settings.PROPERTY_TIMEZONE)
    return datetime.combine(day, _parse_time(hhmm), tzinfo=tz)


def local_date(dt):
    return dt.astimezone(ZoneInfo(settings.PROPERTY_TIMEZONE)).date()


def to_decimal(value, default='0'):
    if value in (None, ''):
        return money(default)
    try:
        return money(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return money(default)


def parse_beds24_datetime(value):
    """'2025-01-31T10:20:30Z' veya '2025-01-31 10:20:30' (UTC) -> aware datetime; olmazsa None."""
    if not value:
        return None
    text = str(value).replace('Z', '+00:00').replace(' ', 'T')
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo('UTC'))
    return dt


def map_status(beds24_status, sub_status=None):
    if sub_status == 'noShow':
        return 'no_show'
    return STATUS_FROM_BEDS24.get((beds24_status or '').lower())


def map_source(booking):
    """Beds24 booking -> Reservation.source. `channel` alanı esas; yoksa apiSource adı."""
    channel = (booking.get('channel') or '').lower()
    if channel in AIRBNB_CHANNELS:
        return 'airbnb'
    if channel in BOOKING_CHANNELS:
        return 'booking'
    if channel in DIRECT_CHANNELS:
        api_source = (booking.get('apiSource') or '').lower()
        if 'airbnb' in api_source:
            return 'airbnb'
        if 'booking.com' in api_source:
            return 'booking'
        # TODO(beds24): doğrula — boş kanal + apiSourceId 0 = Beds24 içi/direkt varsayıldı.
        return 'direct'
    return 'other'


# --------------------------------------------------------------------------- property
def property_payload(prop, listing=None, webhook_url=None):
    """Bir PMS evi = bir Beds24 property + qty=1 olan tek roomType."""
    room = {
        'name': prop.name[:100],
        'roomType': 'apartment',
        'qty': 1,
        'maxPeople': prop.max_guests,
        'maxAdult': prop.max_guests,
        'rackRate': float(money(prop.base_price)),
        'minPrice': 0,
        'roomSize': int(prop.area or 0),
    }
    payload = {
        'name': prop.name[:100],
        'propertyType': 'apartment',
        'currency': settings.PROPERTY_CURRENCY,
        'address': prop.address,
        'city': prop.city,
        'country': prop.country,
        'postcode': prop.postal_code,
        'phone': prop.phone,
        'email': prop.email,
        'checkInStart': settings.DEFAULT_CHECKIN_TIME,
        'checkOutEnd': settings.DEFAULT_CHECKOUT_TIME,
        'texts': [{'language': 'en', 'propertyDescription': prop.description or ''}],
        'roomTypes': [room],
    }
    if listing is not None and listing.external_listing_id:
        payload['id'] = int(listing.external_listing_id)
        if listing.external_room_id:
            room['id'] = int(listing.external_room_id)
    if webhook_url:
        # Webhook gövdesi kişisel veri içermesin; işlerken booking zaten GET ile tekrar çekiliyor.
        payload['webhooks'] = {'version': 'twoNoPersonalData', 'url': webhook_url}
    return payload


def new_id_from_post(result):
    """POST /properties|/bookings cevabındaki yeni kaydın id'si.

    TODO(beds24): doğrula — OpenAPI 'new' nesnesini genel tanımlıyor; pratikte {'id': ...} dönüyor.
    """
    if isinstance(result, list):
        result = result[0] if result else {}
    new = (result or {}).get('new') or {}
    value = new.get('id') if isinstance(new, dict) else None
    return str(value) if value else None


# --------------------------------------------------------------------------- calendar
def calendar_entries(days, airbnb_markup=0, booking_markup=0):
    """DayRate listesi -> Beds24 calendar girişleri; aynı değerli ardışık günler tek aralıkta birleşir.

    Müsaitlik numAvail ile DEĞİL override ile gönderilir: Beds24 rezervasyonları kendisi düşer,
    biz sadece kapalı günleri ('blackout') kapatır, diğerlerini 'none' yaparız. Böylece PMS'in henüz
    görmediği bir Beds24 rezervasyonunun tarihi yanlışlıkla tekrar satışa açılmaz.
    TODO(beds24): doğrula — blackout -> none geçişinde Beds24 numAvail'i kendisi geri hesaplıyor.
    """
    entries = []
    for day in days:
        values = {
            'minStay': day.min_stay,
            'override': 'blackout' if day.closed else 'none',
            PRICE_SLOT_BASE: float(day.price),
            PRICE_SLOT_AIRBNB: float(apply_markup(day.price, airbnb_markup)),
            PRICE_SLOT_BOOKING: float(apply_markup(day.price, booking_markup)),
        }
        iso = day.date.isoformat()
        last = entries[-1] if entries else None
        if last and last['_values'] == values and _next_day(last['to']) == iso:
            last['to'] = iso
        else:
            entries.append({'from': iso, 'to': iso, '_values': values})
    return [{'from': e['from'], 'to': e['to'], **e['_values']} for e in entries]


def _next_day(iso):
    d = date.fromisoformat(iso)
    return date.fromordinal(d.toordinal() + 1).isoformat()


def calendar_payload(room_id, entries):
    return [{'roomId': int(room_id), 'calendar': entries}]


# --------------------------------------------------------------------------- bookings
def booking_dates(booking):
    arrival = date.fromisoformat(booking['arrival'])
    departure = date.fromisoformat(booking['departure'])
    return (
        local_datetime(arrival, settings.DEFAULT_CHECKIN_TIME),
        local_datetime(departure, settings.DEFAULT_CHECKOUT_TIME),
    )


def guest_fields(booking):
    first = (booking.get('firstName') or '').strip()
    last = (booking.get('lastName') or '').strip()
    if not first and not last:
        first, last = 'Guest', str(booking.get('id') or '')
    return {
        'first_name': first[:100] or '-',
        'last_name': last[:100] or '-',
        'email': (booking.get('email') or '').strip()[:254],
        'phone': (booking.get('phone') or booking.get('mobile') or '').strip()[:20],
        'nationality': (booking.get('country2') or booking.get('country') or '')[:100],
    }


CLEANING_KEYWORDS = ('clean', 'temizlik')


def cleaning_fee_from_invoice(booking):
    """Fatura kalemlerinden temizlik ücretini toplar (açıklamada 'clean'/'temizlik' geçen charge'lar).

    TODO(beds24): doğrula — kanal temizlik ücretini ayrı kalem olarak gönderiyor mu.
    """
    total = Decimal('0')
    for item in booking.get('invoiceItems') or []:
        if (item.get('type') or 'charge') != 'charge':
            continue
        if any(k in (item.get('description') or '').lower() for k in CLEANING_KEYWORDS):
            line = item.get('lineTotal')
            if line in (None, ''):
                line = Decimal(str(item.get('amount') or 0)) * Decimal(str(item.get('qty') or 1))
            total += to_decimal(line)
    return money(total)


def finance_fields(booking):
    """Komisyon kanaldan geliyorsa kesin, gelmiyorsa None (PMS kanal oranıyla tahmin eder)."""
    commission = to_decimal(booking.get('commission'))
    return {
        'channel_commission': commission if commission > 0 else None,
        'commission_is_estimated': False,
        'taxes': max(to_decimal(booking.get('tax')), Decimal('0')),
        'cleaning_fee': cleaning_fee_from_invoice(booking),
    }


def reservation_fields(booking):
    """Beds24 booking -> Reservation alanları (property/guest/status hariç)."""
    check_in, check_out = booking_dates(booking)
    special = '\n'.join(x for x in (booking.get('comments'), booking.get('message')) if x)
    return {
        **finance_fields(booking),
        'check_in': check_in,
        'check_out': check_out,
        'adults': max(int(booking.get('numAdult') or 1), 1),
        'children': max(int(booking.get('numChild') or 0), 0),
        'total_price': max(to_decimal(booking.get('price')), Decimal('0')),
        'currency': settings.PROPERTY_CURRENCY,
        'source': map_source(booking),
        'external_source_id': str(booking['id']),
        'channel_booking_ref': str(booking.get('apiReference') or '')[:100],
        'guest_language': str(booking.get('lang') or '')[:10].lower(),
        'special_requests': special[:2000],
    }


def reservation_to_booking(reservation, room_id):
    """PMS (direkt) rezervasyonu -> Beds24 POST /bookings öğesi."""
    guest = reservation.guest
    payload = {
        'roomId': int(room_id),
        'status': STATUS_TO_BEDS24.get(reservation.status, 'confirmed'),
        'arrival': local_date(reservation.check_in).isoformat(),
        'departure': local_date(reservation.check_out).isoformat(),
        'numAdult': reservation.adults,
        'numChild': reservation.children,
        'firstName': guest.first_name,
        'lastName': guest.last_name,
        'email': guest.email,
        'phone': guest.phone,
        'price': float(money(reservation.total_price)),
        'apiReference': str(reservation.id),
        'actions': {'allowWebhooks': True},
    }
    if reservation.source != 'direct':
        # PMS'e elle girilmiş kanal rezervasyonu: Beds24 panelinde nereden geldiği görünsün.
        payload['referer'] = f'PMS ({reservation.get_source_display()})'
    if reservation.external_source_id:
        payload['id'] = int(reservation.external_source_id)
    return payload
