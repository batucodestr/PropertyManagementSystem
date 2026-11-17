"""Temizlik otomasyonu.

- Rezervasyon confirmed olunca check-out günü için tek bir otomatik temizlik görevi açılır
  (atanan = evin varsayılan temizlikçisi).
- Tarih/ev değişince bekleyen görev taşınır. İptal / no-show / pending'e dönüşte bekleyen görev silinir.
  Başlamış veya bitmiş görevlere dokunulmaz.
- Aynı gün aynı eve giriş varsa görev 'urgent' olur (yeni giriş eklenince/kalkınca yeniden hesaplanır).
- Ev durumu: check-out (completed) -> dirty, görev başladı -> cleaning, görev bitti -> ready.
  Property.save() kanal senkronu tetiklediği için durum .update() ile yazılır.
"""
from django.db import transaction
from django.utils import timezone

from apps.properties.models import Property
from apps.properties.pricing import property_tz
from apps.reservations.models import Reservation

from .models import HouseKeepingTasks

TASK_STATUSES = ('confirmed', 'completed')
CHECKIN_STATUSES = ('pending', 'confirmed')


def local_date(dt):
    return dt.astimezone(property_tz()).date()


def refresh_priority(property_id, day):
    """O gün o eve giriş varsa açık temizlik görevlerini urgent, yoksa normal yapar."""
    if not property_id or not day:
        return
    tz = property_tz()
    same_day_checkin = any(
        r.astimezone(tz).date() == day
        for r in Reservation.objects.filter(
            property_id=property_id, status__in=CHECKIN_STATUSES,
            check_in__date__gte=day - timezone.timedelta(days=1),
            check_in__date__lte=day + timezone.timedelta(days=1),
        ).values_list('check_in', flat=True)
    )
    priority = HouseKeepingTasks.Priority.URGENT if same_day_checkin else HouseKeepingTasks.Priority.NORMAL
    HouseKeepingTasks.objects.filter(
        property_id=property_id, scheduled_date=day, status__in=('pending', 'in_progress'),
    ).exclude(priority=priority).update(priority=priority)


def sync_checkout_task(reservation, old=None):
    """Rezervasyonun otomatik check-out temizliğini güncel durumla eşitler (idempotent)."""
    with transaction.atomic():
        task = (
            HouseKeepingTasks.objects.select_for_update()
            .filter(reservation=reservation, is_auto=True).first()
        )
        checkout_day = local_date(reservation.check_out)
        if reservation.status in TASK_STATUSES:
            if task is None:
                if reservation.status == 'confirmed':
                    HouseKeepingTasks.objects.create(
                        property=reservation.property, reservation=reservation, is_auto=True,
                        scheduled_date=checkout_day,
                        assigned_to_id=reservation.property.default_cleaner_id,
                    )
            elif task.status == HouseKeepingTasks.Status.PENDING and (
                task.scheduled_date != checkout_day or task.property_id != reservation.property_id
            ):
                task.scheduled_date = checkout_day
                task.property_id = reservation.property_id
                task.save(update_fields=['scheduled_date', 'property', 'updated_at'])
        elif task is not None and task.status == HouseKeepingTasks.Status.PENDING:
            task.delete()

    # Bu rezervasyonun check-out (görev) ve check-in (başkasının görevi) günlerinin önceliği.
    days = {(reservation.property_id, checkout_day), (reservation.property_id, local_date(reservation.check_in))}
    if old:
        days |= {(old['property_id'], local_date(old['check_out'])), (old['property_id'], local_date(old['check_in']))}
    for property_id, day in days:
        refresh_priority(property_id, day)


def set_property_status(property_id, status):
    Property.objects.filter(pk=property_id).exclude(housekeeping_status=status).update(housekeeping_status=status)
