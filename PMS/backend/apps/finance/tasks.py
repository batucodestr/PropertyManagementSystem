from celery import shared_task

from . import services


@shared_task
def generate_recurring_expenses():
    return services.generate_recurring_expenses()
