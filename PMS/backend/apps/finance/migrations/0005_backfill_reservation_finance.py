"""Mevcut rezervasyonlar için komisyon/net hesaplar ve gelir kayıtlarını oluşturur.

Kurallar apps.finance.services ile aynıdır (net = toplam - komisyon - vergi; confirmed/completed -> gelir).
"""
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations


def money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def forwards(apps, schema_editor):
    Reservation = apps.get_model('reservations', 'Reservation')
    FinancialTransaction = apps.get_model('finance', 'FinancialTransaction')
    tz = ZoneInfo(settings.PROPERTY_TIMEZONE)
    for r in Reservation.objects.select_related('guest').iterator():
        rate = Decimal(str(settings.CHANNEL_COMMISSIONS.get(r.source, 0)))
        if r.channel_commission is None:
            r.channel_commission = money(Decimal(r.total_price) * rate / 100)
            r.commission_is_estimated = rate > 0
        r.net_amount = money(Decimal(r.total_price) - r.channel_commission - Decimal(r.taxes or 0))
        r.save(update_fields=['channel_commission', 'commission_is_estimated', 'net_amount'])
        if r.status in ('confirmed', 'completed') and r.net_amount > 0:
            FinancialTransaction.objects.update_or_create(
                reservation=r, category='reservation',
                defaults={
                    'property_id': r.property_id,
                    'transaction_type': 'income',
                    'amount': r.net_amount,
                    'currency': r.currency,
                    'transaction_date': r.check_in.astimezone(tz).date(),
                    'description': f'Reservation – {r.guest.first_name} {r.guest.last_name} (backfill)',
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_financialtransaction_general_task_and_more'),
        ('reservations', '0005_reservation_channel_commission_and_more'),
        ('operations', '0002_generaltask_cost_housekeepingtasks_cost'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
