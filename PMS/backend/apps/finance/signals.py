from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.operations.models import GeneralTask, HouseKeepingTasks
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


@receiver(post_save, sender=HouseKeepingTasks, dispatch_uid='finance_housekeeping_expense')
def housekeeping_expense(sender, instance, **kwargs):
    services.sync_task_expense(
        instance, link_field='housekeeping_task', category='cleaning',
        label=f'Cleaning – {instance.property.name} ({instance.scheduled_date})',
    )


@receiver(post_save, sender=GeneralTask, dispatch_uid='finance_general_task_expense')
def general_task_expense(sender, instance, **kwargs):
    services.sync_task_expense(
        instance, link_field='general_task', category='maintenance',
        label=f'Maintenance – {instance.description[:80]}',
    )
