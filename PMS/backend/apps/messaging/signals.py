from datetime import datetime, time

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.reservations.models import Reservation

from . import services


def _as_datetime(value):
    if isinstance(value, str):
        value = parse_datetime(value) or datetime.combine(parse_date(value[:10]), time())
    return timezone.make_aware(value) if timezone.is_naive(value) else value


@receiver(post_save, sender=Reservation, dispatch_uid='messaging_reservation_schedule')
def reservation_messages(sender, instance, **kwargs):
    instance.check_in = _as_datetime(instance.check_in)
    instance.check_out = _as_datetime(instance.check_out)
    services.schedule_for_reservation(instance)
