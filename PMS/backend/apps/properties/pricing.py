"""Gün bazlı etkin fiyat ve müsaitlik hesabı (kanal yöneticisinden bağımsız).

Öncelik: DailyRate > SeasonalRate (hafta sonu geceleri weekend_price) > Property.base_price.
Gece d dolu sayılır: bloklayan statüde bir rezervasyon için check_in(yerel gün) <= d < check_out(yerel gün),
ya da AvailabilityBlock için start_date <= d <= end_date.
Kapalı: DailyRate.closed, AvailabilityBlock veya pasif ev. Kapalı geceler kanallarda satışa kapatılır.
"""
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings

TWO_PLACES = Decimal('0.01')
DEFAULT_MIN_STAY = 1


def money(value):
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def apply_markup(price, percent):
    """price * (1 + percent/100), Decimal ve ROUND_HALF_UP ile 2 hane."""
    return money(Decimal(price) * (Decimal('1') + Decimal(percent or 0) / Decimal('100')))


def suggested_markup(commission_percent):
    """Komisyon sonrası aynı neti almak için gereken markup (%): 1/(1-c) - 1."""
    c = Decimal(commission_percent) / Decimal('100')
    return money((Decimal('1') / (Decimal('1') - c) - Decimal('1')) * Decimal('100'))


def property_tz():
    return ZoneInfo(settings.PROPERTY_TIMEZONE)


def daterange(start, end):
    """start..end (ikisi de dahil)."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


@dataclass
class DayRate:
    date: date
    price: Decimal
    min_stay: int
    closed: bool
    available: bool
    source: str  # daily | seasonal | weekend | base
    reason: str = ''  # kapalı/dolu ise neden: closed | block | reservation | inactive

    def as_dict(self):
        data = asdict(self)
        data['date'] = self.date.isoformat()
        data['price'] = str(self.price)
        return data


def occupied_nights(property, date_from, date_to):
    """Bloklayan rezervasyonların doldurduğu gecelerin kümesi (yerel tarih)."""
    from apps.reservations.models import Reservation
    from apps.reservations.serializers import BLOCKING_STATUSES

    tz = property_tz()
    nights = set()
    qs = Reservation.objects.filter(
        property=property, status__in=BLOCKING_STATUSES,
        check_in__date__lte=date_to + timedelta(days=1),
        check_out__date__gte=date_from - timedelta(days=1),
    ).only('check_in', 'check_out')
    for r in qs:
        start = r.check_in.astimezone(tz).date()
        end = r.check_out.astimezone(tz).date()
        day = max(start, date_from)
        while day < end and day <= date_to:
            nights.add(day)
            day += timedelta(days=1)
    return nights


def blocked_days(property, date_from, date_to):
    from apps.reservations.models import AvailabilityBlock

    days = set()
    for block in AvailabilityBlock.objects.filter(
        property=property, start_date__lte=date_to, end_date__gte=date_from,
    ):
        for day in daterange(max(block.start_date, date_from), min(block.end_date, date_to)):
            days.add(day)
    return days


def calendar(property, date_from, date_to):
    """date_from..date_to (dahil) için gün gün DayRate listesi."""
    from .models import DailyRate, SeasonalRate

    daily = {d.date: d for d in DailyRate.objects.filter(property=property, date__range=(date_from, date_to))}
    seasons = list(
        SeasonalRate.objects.filter(property=property, start_date__lte=date_to, end_date__gte=date_from)
        .order_by('-start_date', '-created_at')  # çakışmada en son başlayan sezon kazanır
    )
    occupied = occupied_nights(property, date_from, date_to)
    blocks = blocked_days(property, date_from, date_to)
    weekend = set(settings.WEEKEND_NIGHTS)

    days = []
    for day in daterange(date_from, date_to):
        price = money(property.base_price)
        min_stay = DEFAULT_MIN_STAY
        source = 'base'
        season = next((s for s in seasons if s.start_date <= day <= s.end_date), None)
        if season:
            if season.weekend_price is not None and day.weekday() in weekend:
                price, source = money(season.weekend_price), 'weekend'
            else:
                price, source = money(season.nightly_price), 'seasonal'
            if season.min_stay:
                min_stay = season.min_stay
        override = daily.get(day)
        closed = False
        if override:
            if override.price is not None:
                price, source = money(override.price), 'daily'
            if override.min_stay:
                min_stay = override.min_stay
            closed = override.closed

        reason = ''
        if not property.is_active:
            reason = 'inactive'
        elif closed:
            reason = 'closed'
        elif day in blocks:
            reason = 'block'
        elif day in occupied:
            reason = 'reservation'
        days.append(DayRate(
            date=day, price=price, min_stay=min_stay,
            closed=reason in ('inactive', 'closed', 'block'),
            available=not reason, source=source, reason=reason,
        ))
    return days
