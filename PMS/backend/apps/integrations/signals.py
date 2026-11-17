"""PMS kayıtları değişince kanal yöneticisi senkron task'larını kuyruğa atar.

Kaydetme asla dış API çağrısına bağlı değildir: task'lar transaction commit edildikten sonra
kuyruğa atılır; kuyruk (Redis) erişilemezse sadece loglanır, gece senkronu ve elle senkron telafi eder.
"""
import logging
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.properties.models import DailyRate, Property, SeasonalRate
from apps.properties.signals import rates_changed
from apps.reservations.models import AvailabilityBlock, Reservation

logger = logging.getLogger(__name__)


def enqueue(task, *args):
    """Commit sonrası task.delay(*args); broker hatası isteği bozmaz."""
    if not settings.BEDS24_AUTO_SYNC:
        return

    def _send():
        try:
            task.delay(*args)
        except Exception as exc:  # Redis kapalı vb.
            logger.warning('Senkron task kuyruğa atılamadı (%s): %s', task.name, exc.__class__.__name__)

    transaction.on_commit(_send)


def _as_date(value):
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return value


def _iso(value):
    value = _as_date(value)
    return value.isoformat() if value else None


@receiver(post_save, sender=Property, dispatch_uid='beds24_property_saved')
def property_saved(sender, instance, **kwargs):
    from .beds24.tasks import sync_property_task

    enqueue(sync_property_task, str(instance.pk))


def _rates_changed(instance, start, end):
    from .beds24.tasks import push_rates_task

    enqueue(push_rates_task, str(instance.property_id), _iso(start), _iso(end))


@receiver(post_save, sender=SeasonalRate, dispatch_uid='beds24_seasonal_saved')
@receiver(post_delete, sender=SeasonalRate, dispatch_uid='beds24_seasonal_deleted')
@receiver(post_save, sender=AvailabilityBlock, dispatch_uid='beds24_block_saved')
@receiver(post_delete, sender=AvailabilityBlock, dispatch_uid='beds24_block_deleted')
def range_changed(sender, instance, **kwargs):
    old = getattr(instance, '_old_range', None)
    start, end = _as_date(instance.start_date), _as_date(instance.end_date)
    if old:
        start, end = min(start, old[0]), max(end, old[1])
    _rates_changed(instance, start, end)


@receiver(pre_save, sender=SeasonalRate, dispatch_uid='beds24_seasonal_pre')
@receiver(pre_save, sender=AvailabilityBlock, dispatch_uid='beds24_block_pre')
def remember_range(sender, instance, **kwargs):
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).values_list('start_date', 'end_date').first()
        instance._old_range = old


@receiver(post_save, sender=DailyRate, dispatch_uid='beds24_daily_saved')
@receiver(post_delete, sender=DailyRate, dispatch_uid='beds24_daily_deleted')
def daily_changed(sender, instance, **kwargs):
    if getattr(instance, '_skip_push', False):
        return  # Toplu güncellemede tek bir push yapılır.
    _rates_changed(instance, instance.date, instance.date)


@receiver(rates_changed, dispatch_uid='beds24_rates_bulk')
def bulk_rates_changed(sender, property, date_from, date_to, **kwargs):
    from .beds24.tasks import push_rates_task

    enqueue(push_rates_task, str(property.pk), _iso(date_from), _iso(date_to))


@receiver(post_save, sender=Reservation, dispatch_uid='beds24_reservation_saved')
def reservation_saved(sender, instance, **kwargs):
    """PMS'te oluşturulan/değişen rezervasyon -> Beds24 booking (kanallarda tarih kapanır)."""
    from .beds24.tasks import push_booking_task

    if getattr(instance, '_from_channel', False):
        return  # Kanaldan gelen güncelleme geri gönderilmez (döngü olmasın).
    if instance.created_via_channel:
        return  # Beds24'ten içe aktarılan (OTA) rezervasyon zaten orada; kanal verisi otoriter.
    # PMS'te açılan her rezervasyon (kaynağı Airbnb/Booking seçilmiş olsa bile) Beds24'e gider,
    # böylece diğer kanallarda tarih kapanır.
    enqueue(push_booking_task, str(instance.pk))


@receiver(post_delete, sender=Reservation, dispatch_uid='beds24_reservation_deleted')
def reservation_deleted(sender, instance, **kwargs):
    """PMS'te açılıp Beds24'e gönderilmiş rezervasyon silinince Beds24 kaydı da silinir (tarih açılır).
    Beds24'ten gelen OTA rezervasyonlarına dokunulmaz: onları sadece kanal (Airbnb/Booking) iptal edebilir."""
    from .beds24.tasks import delete_booking_task

    if instance.created_via_channel or not instance.external_source_id:
        return
    enqueue(delete_booking_task, instance.external_source_id)
