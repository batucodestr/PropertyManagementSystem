"""1) Beds24'ten içe aktarılmış rezervasyonları işaretler (Beds24 id'si var ve kaynak direkt değil).
2) PMS formundan sadece tarih gönderildiği için UTC 00:00'a kaydedilmiş giriş/çıkışları ev saat
   dilimindeki varsayılan saatlere (ör. 15:00 / 11:00) taşır.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations


def _hm(value):
    hour, minute = value.split(':')
    return time(int(hour), int(minute))


def forwards(apps, schema_editor):
    Reservation = apps.get_model('reservations', 'Reservation')
    Reservation.objects.exclude(external_source_id='').exclude(source='direct').update(created_via_channel=True)

    tz = ZoneInfo(settings.PROPERTY_TIMEZONE)
    utc = ZoneInfo('UTC')
    check_in_time = _hm(settings.DEFAULT_CHECKIN_TIME)
    check_out_time = _hm(settings.DEFAULT_CHECKOUT_TIME)
    for r in Reservation.objects.filter(created_via_channel=False).iterator():
        changed = []
        for field, default in (('check_in', check_in_time), ('check_out', check_out_time)):
            value = getattr(r, field).astimezone(utc)
            if (value.hour, value.minute, value.second) == (0, 0, 0):
                setattr(r, field, datetime.combine(value.date(), default, tzinfo=tz))
                changed.append(field)
        if changed and r.check_out > r.check_in:
            r.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [('reservations', '0007_reservation_created_via_channel')]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
