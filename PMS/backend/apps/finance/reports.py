"""Finans özeti (tamamen otomatik, rezervasyonlardan): brüt, komisyon, vergi, net; ev ve kanal kırılımı;
doluluk, ADR, RevPAR.

Gelir dağıtımı GECE BAZINDA oranlanır: 5 gecelik bir rezervasyonun 2 gecesi aralıktaysa tutarlarının
2/5'i bu aralığa yazılır. Böylece ay sınırını aşan konaklamalar doğru ayrılır ve doluluk / ADR / RevPAR
aynı temelden hesaplanır.
    ADR    = brüt konaklama geliri / satılan gece
    RevPAR = brüt konaklama geliri / satılabilir gece (aktif ev sayısı x gün)
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from apps.properties.models import Property
from apps.properties.pricing import money, property_tz
from apps.reservations.models import Reservation

from .services import INCOME_STATUSES

ZERO = Decimal('0')
VALUE_KEYS = ('gross', 'commission', 'taxes', 'net')


def _bucket():
    return {'gross': ZERO, 'commission': ZERO, 'taxes': ZERO, 'net': ZERO, 'nights': 0, 'reservations': 0}


def _month_key(day):
    return day.strftime('%Y-%m')


def _months(date_from, date_to):
    keys, day = [], date_from.replace(day=1)
    while day <= date_to:
        keys.append(_month_key(day))
        day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return keys


def _ratio(numerator, denominator):
    return money(Decimal(numerator) / Decimal(denominator)) if denominator else money(0)


def summary(date_from, date_to, property_id=None):
    tz = property_tz()
    days = (date_to - date_from).days + 1
    props = Property.objects.all()
    if property_id:
        props = props.filter(pk=property_id)
    prop_names = {p.pk: p.name for p in props}
    active_count = props.filter(is_active=True).count() if not property_id else props.count()

    total = _bucket()
    by_property = defaultdict(_bucket)
    by_channel = defaultdict(_bucket)
    by_month = defaultdict(_bucket)

    reservations = Reservation.objects.filter(
        status__in=INCOME_STATUSES,
        check_in__date__lte=date_to + timedelta(days=1),
        check_out__date__gte=date_from - timedelta(days=1),
    )
    if property_id:
        reservations = reservations.filter(property_id=property_id)

    for r in reservations:
        ci = r.check_in.astimezone(tz).date()
        co = r.check_out.astimezone(tz).date()
        nights_total = max((co - ci).days, 1)
        start, end = max(ci, date_from), min(co - timedelta(days=1), date_to)
        if start > end:
            continue
        nights_by_month = defaultdict(int)
        day = start
        while day <= end:
            nights_by_month[_month_key(day)] += 1
            day += timedelta(days=1)
        nights_in = sum(nights_by_month.values())
        values = {
            'gross': Decimal(r.total_price),
            'commission': Decimal(r.channel_commission or 0),
            'taxes': Decimal(r.taxes or 0),
            'net': Decimal(r.net_amount or 0),
        }
        for bucket in (total, by_property[r.property_id], by_channel[r.source]):
            for key, amount in values.items():
                bucket[key] += amount * nights_in / nights_total
            bucket['nights'] += nights_in
            bucket['reservations'] += 1
        for month, nights in nights_by_month.items():
            for key, amount in values.items():
                by_month[month][key] += amount * nights / nights_total
            by_month[month]['nights'] += nights

    def finish(bucket, available=None):
        out = {k: str(money(bucket[k])) for k in VALUE_KEYS}
        out['nights'] = bucket['nights']
        out['reservations'] = bucket['reservations']
        out['adr'] = str(_ratio(bucket['gross'], bucket['nights']))
        if available is not None:
            out['available_nights'] = available
            out['occupancy'] = str(_ratio(Decimal(bucket['nights']) * 100, available))
            out['revpar'] = str(_ratio(bucket['gross'], available))
        return out

    return {
        'from': date_from.isoformat(),
        'to': date_to.isoformat(),
        'property': str(property_id) if property_id else None,
        'totals': finish(total, active_count * days),
        'by_property': [
            {'property': str(pk), 'name': name, **finish(by_property[pk], days)}
            for pk, name in sorted(prop_names.items(), key=lambda kv: kv[1])
        ],
        'by_channel': [
            {'source': source, **finish(by_channel[source])}
            for source in ('direct', 'airbnb', 'booking', 'other')
        ],
        'by_month': [
            {'month': m, **{k: str(money(by_month[m][k])) for k in ('gross', 'commission', 'net')},
             'nights': by_month[m]['nights']}
            for m in _months(date_from, date_to)
        ],
    }


def default_range(today=None):
    today = today or date.today()
    first = today.replace(day=1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last
