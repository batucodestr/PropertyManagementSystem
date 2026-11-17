from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import django_filters
from django.conf import settings

from .models import Reservation


def _local_day_range(day):
    """Ev saat dilimindeki bir günün [00:00, ertesi 00:00) aralığı (aware)."""
    tz = ZoneInfo(settings.PROPERTY_TIMEZONE)
    start = datetime.combine(day, time(), tzinfo=tz)
    return start, start + timedelta(days=1)


class ReservationFilter(django_filters.FilterSet):
    """check_in_date / check_out_date: ev saat dilimine göre o gün giriş / çıkış yapanlar.

    check_in / check_out tarih-saat alanlarıdır; '?check_in=2030-07-01' sadece 00:00'ı eşler,
    bugünün girişleri için check_in_date kullanılmalı.
    """
    check_in_date = django_filters.DateFilter(method='filter_local_day')
    check_out_date = django_filters.DateFilter(method='filter_local_day')

    class Meta:
        model = Reservation
        fields = {
            'property': ['exact'],
            'guest': ['exact'],
            'status': ['exact'],
            'source': ['exact'],
            'check_in': ['exact', 'gte', 'lte'],
            'check_out': ['exact', 'gte', 'lte'],
        }

    def filter_local_day(self, queryset, name, value):
        start, end = _local_day_range(value)
        field = name.removesuffix('_date')
        return queryset.filter(**{f'{field}__gte': start, f'{field}__lt': end})
