from django.db import models

from apps.core.models import BaseModel
from apps.reservations.models import Reservation


class Conversation(BaseModel):
    """Rezervasyon başına tek konuşma (kanal: Airbnb / Booking.com / e-posta ...)."""
    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name='conversation')
    channel = models.CharField(max_length=20)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=200, blank=True)
    unread_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-last_message_at']


class Message(BaseModel):
    class Direction(models.TextChoices):
        IN = 'in', 'Incoming'
        OUT = 'out', 'Outgoing'

    class Status(models.TextChoices):
        RECEIVED = 'received', 'Received'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    class Source(models.TextChoices):
        GUEST = 'guest', 'Guest'
        HOST = 'host', 'Host'
        SYSTEM = 'system', 'Channel / system'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=3, choices=Direction.choices)
    source = models.CharField(max_length=10, choices=Source.choices)
    body = models.TextField()
    sent_at = models.DateTimeField()
    # Kanal (Beds24) mesaj id'si: aynı mesaj iki kez içe aktarılmaz.
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    is_read = models.BooleanField(default=True)
    sent_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['sent_at', 'created_at']
