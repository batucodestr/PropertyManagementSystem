from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.properties.models import Property
from apps.reservations.models import Reservation

from . import housekeeping
from .models import HouseKeepingTasks


def _as_datetime(value):
    """Kaydedilmiş ama DB'den okunmamış instance'larda tarih string ('2030-06-10' gibi) olabilir."""
    if isinstance(value, str):
        value = parse_datetime(value) or datetime.combine(parse_date(value[:10]), time())
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


@receiver(pre_save, sender=Reservation, dispatch_uid='operations_reservation_pre')
def remember_reservation(sender, instance, **kwargs):
    instance._ops_old = None
    if instance.pk:
        instance._ops_old = (
            Reservation.objects.filter(pk=instance.pk)
            .values('property_id', 'check_in', 'check_out', 'status').first()
        )


@receiver(post_save, sender=Reservation, dispatch_uid='operations_reservation_post')
def reservation_housekeeping(sender, instance, **kwargs):
    # Kaydedilmiş ama DB'den okunmamış instance'larda tarih string olabilir.
    instance.check_in = _as_datetime(instance.check_in)
    instance.check_out = _as_datetime(instance.check_out)
    old = getattr(instance, '_ops_old', None)
    housekeeping.sync_checkout_task(instance, old)
    if instance.status == 'completed' and (not old or old['status'] != 'completed'):
        housekeeping.set_property_status(instance.property_id, Property.HousekeepingStatus.DIRTY)


@receiver(post_save, sender=HouseKeepingTasks, dispatch_uid='operations_housekeeping_status')
def housekeeping_property_status(sender, instance, **kwargs):
    if instance.status == HouseKeepingTasks.Status.IN_PROGRESS:
        housekeeping.set_property_status(instance.property_id, Property.HousekeepingStatus.CLEANING)
    elif instance.status == HouseKeepingTasks.Status.COMPLETED:
        housekeeping.set_property_status(instance.property_id, Property.HousekeepingStatus.READY)
