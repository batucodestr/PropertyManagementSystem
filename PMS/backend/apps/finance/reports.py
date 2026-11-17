"""Finans özeti: gelir, komisyon, net, masraf, kâr; ev ve kanal kırılımı; doluluk, ADR, RevPAR.

Gelir dağıtımı GECE BAZINDA oranlanır: 5 gecelik bir rezervasyonun 2 gecesi aralıktaysa tutarlarının
2/5'i bu aralığa yazılır. Böylece ay sınırını aşan konaklamalar doğru ayrılır ve doluluk / ADR / RevPAR
aynı temelden hesaplanır.
    ADR    = brüt konaklama geliri / satılan gece
    RevPAR = brüt konaklama geliri / satılabilir gece (aktif ev sayısı x gün)
Masraflar transaction_date'e göre; kâr = net konaklama geliri + diğer gelir - masraf.
Otomatik "reservation" gelir kayıtları burada toplanmaz (rezervasyondan hesaplandığı için çift sayım olur).
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.properties.models import Property
from apps.properties.pricing import money, property_tz
from apps.reservations.models import Reservation

from .models import FinancialTransaction
from .services import INCOME_STATUSES

ZERO = Decimal('0')
MONEY_KEYS = ('gross', 'commission', 'taxes', 'net', 'expenses', 'other_income', 'profit')


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
    by_month = defaultdict(lambda: {**_bucket(), 'expenses': ZERO})

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
        targets = [total, by_property[r.property_id], by_channel[r.source]]
        for bucket in targets:
            for key, amount in values.items():
                bucket[key] += amount * nights_in / nights_total
            bucket['nights'] += nights_in
            bucket['reservations'] += 1
        for month, nights in nights_by_month.items():
            for key, amount in values.items():
                by_month[month][key] += amount * nights / nights_total
            by_month[month]['nights'] += nights

    tx = FinancialTransaction.objects.filter(transaction_date__range=(date_from, date_to))
    if property_id:
        tx = tx.filter(property_id=property_id)
    expenses_qs = tx.filter(transaction_type='expense')
    other_income_qs = tx.filter(transaction_type='income').exclude(category='reservation')

    expenses_total = expenses_qs.aggregate(s=Sum('amount'))['s'] or ZERO
    other_income_total = other_income_qs.aggregate(s=Sum('amount'))['s'] or ZERO
    expenses_by_property = dict(expenses_qs.values_list('property').annotate(s=Sum('amount')))
    other_by_property = dict(other_income_qs.values_list('property').annotate(s=Sum('amount')))
    expenses_by_category = {
        row['category']: str(money(row['s']))
        for row in expenses_qs.values('category').annotate(s=Sum('amount')).order_by('-s')
    }
    for row in expenses_qs.values('transaction_date', 'amount'):
        by_month[_month_key(row['transaction_date'])]['expenses'] += row['amount']

    available_nights = active_count * days

    def finish(bucket, expenses=ZERO, other_income=ZERO, available=None):
        out = {k: str(money(bucket[k])) for k in ('gross', 'commission', 'taxes', 'net')}
        out['expenses'] = str(money(expenses))
        out['other_income'] = str(money(other_income))
        out['profit'] = str(money(bucket['net'] + other_income - expenses))
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
        'totals': finish(total, expenses_total, other_income_total, available_nights),
        'expenses_by_category': expenses_by_category,
        'by_property': [
            {
                'property': str(pk), 'name': name,
                **finish(by_property[pk], expenses_by_property.get(pk, ZERO), other_by_property.get(pk, ZERO), days),
            }
            for pk, name in sorted(prop_names.items(), key=lambda kv: kv[1])
        ],
        'by_channel': [
            {'source': source, **finish(by_channel[source])}
            for source in ('direct', 'airbnb', 'booking', 'other')
        ],
        'by_month': [
            {'month': m, **{k: str(money(by_month[m][k])) for k in ('gross', 'commission', 'net', 'expenses')},
             'profit': str(money(by_month[m]['net'] - by_month[m]['expenses'])), 'nights': by_month[m]['nights']}
            for m in _months(date_from, date_to)
        ],
    }


def default_range(today=None):
    today = today or date.today()
    first = today.replace(day=1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last
