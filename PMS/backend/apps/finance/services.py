"""Finans kuralları (tek yerde, testle sabitlenmiş).

Rezervasyon:
    net_amount = total_price - channel_commission - taxes
    cleaning_fee total_price'ın İÇİNDEDİR; bilgi amaçlı tutulur, net'ten ayrıca düşülmez.
    Komisyon kanaldan gelmezse kanal varsayılan oranıyla tahmin edilir (commission_is_estimated=True)
    ve fiyat değiştikçe yeniden hesaplanır. Elle/kanaldan girilen komisyon sabit kalır.

Gelir defteri (FinancialTransaction, category=reservation):
    Rezervasyon confirmed/completed ise tek bir gelir kaydı vardır (tutar = net_amount,
    tarih = check-in günü). Pending'de kayıt yoktur. İptal / no-show olunca kayıt SİLİNİR
    (ters kayıt atılmaz): defter her zaman rezervasyonun güncel durumunu yansıtır.

Finans tamamen otomatiktir: elle gelir/masraf girilmez, komisyon elle düzeltilmez.

Tüm para hesapları Decimal, ROUND_HALF_UP, 2 hane.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.properties.pricing import money, property_tz

from .models import FinancialTransaction

INCOME_STATUSES = ('confirmed', 'completed')
ZERO = Decimal('0.00')
Category = FinancialTransaction.Category


def commission_rate(source):
    return Decimal(str(settings.CHANNEL_COMMISSIONS.get(source, 0)))


def estimate_commission(total_price, source):
    return money(Decimal(total_price or 0) * commission_rate(source) / Decimal('100'))


def apply_financials(reservation):
    """Komisyon (gerekirse tahmin) ve net tutarı rezervasyon üzerinde hesaplar (kaydetmez)."""
    if reservation.channel_commission is None or reservation.commission_is_estimated:
        rate = commission_rate(reservation.source)
        reservation.channel_commission = estimate_commission(reservation.total_price, reservation.source)
        reservation.commission_is_estimated = rate > 0
    reservation.channel_commission = money(reservation.channel_commission)
    reservation.taxes = money(reservation.taxes or 0)
    reservation.cleaning_fee = money(reservation.cleaning_fee or 0)
    reservation.net_amount = money(
        Decimal(reservation.total_price or 0) - reservation.channel_commission - reservation.taxes
    )
    return reservation


def _local_date(value):
    if isinstance(value, str):  # kaydedilmiş ama henüz DB'den okunmamış instance
        parsed = parse_datetime(value)
        if parsed is None:
            return date.fromisoformat(value[:10])
        value = parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    return value.astimezone(property_tz()).date()


def sync_reservation_income(reservation):
    """Gelir kaydını rezervasyonun güncel durumuyla eşitler (idempotent)."""
    qs = FinancialTransaction.objects.filter(reservation=reservation, category=Category.RESERVATION)
    if reservation.status not in INCOME_STATUSES or reservation.net_amount <= 0:
        qs.delete()
        return None
    guest = reservation.guest
    description = (
        f'{reservation.get_source_display()} reservation – {guest.first_name} {guest.last_name}. '
        f'Gross {reservation.total_price}, commission {reservation.channel_commission}'
        f'{" (estimated)" if reservation.commission_is_estimated else ""}, taxes {reservation.taxes}.'
    )
    with transaction.atomic():
        tx, _ = FinancialTransaction.objects.select_for_update().update_or_create(
            reservation=reservation, category=Category.RESERVATION,
            defaults={
                'property': reservation.property,
                'transaction_type': FinancialTransaction.TransactionType.INCOME,
                'amount': reservation.net_amount,
                'currency': reservation.currency,
                'transaction_date': _local_date(reservation.check_in),
                'description': description,
            },
        )
    return tx
