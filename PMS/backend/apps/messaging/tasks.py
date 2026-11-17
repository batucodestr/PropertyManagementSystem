from celery import shared_task

from . import services


@shared_task
def send_due_messages():
    return services.send_due_messages()
