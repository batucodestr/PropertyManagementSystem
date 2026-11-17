from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.reservations.models import Reservation

from . import services

FINANCE_FIELDS = ('channel_commission', 'commission_is_estimated', 'cleaning_fee', 'taxes', 'net_amount')


@receiver(pre_save, sender=Reservation, dispatch_uid='finance_reservation_pre_save')
def reservation_financials(sender, instance, **kwargs):
    services.apply_financials(instance)


@receiver(post_save, sender=Reservation, dispatch_uid='finance_reservation_post_save')
def reservation_income(sender, instance, update_fields=None, **kwargs):
    if update_fields is not None and not set(FINANCE_FIELDS) <= set(update_fields):
        # save(update_fields=...) hesaplanan finans alanlarını yazmamış olabilir.
        Reservation.objects.filter(pk=instance.pk).update(**{f: getattr(instance, f) for f in FINANCE_FIELDS})
    services.sync_reservation_income(instance)
