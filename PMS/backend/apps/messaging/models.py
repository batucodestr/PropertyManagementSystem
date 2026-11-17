from django.db import models

from apps.core.models import BaseModel
from apps.reservations.models import Reservation


class MessageTemplate(BaseModel):
    """Otomatik misafir mesajı şablonu.

    Gövdede kullanılabilen değişkenler: {guest_first_name}, {guest_last_name}, {property_name},
    {check_in_date}, {check_in_time}, {check_out_date}, {check_out_time}, {nights}, {address},
    {wifi_name}, {wifi_password}, {door_code}, {check_in_instructions}, {house_rules}, {booking_ref}
    """

    class Trigger(models.TextChoices):
        BOOKING_CONFIRMED = 'booking_confirmed', 'Booking confirmed'
        BEFORE_CHECK_IN = 'before_check_in', 'Hours before check-in'
        CHECK_IN_DAY = 'check_in_day', 'Check-in day'
        CHECK_OUT_MORNING = 'check_out_morning', 'Check-out morning'
        AFTER_CHECK_OUT = 'after_check_out', 'Hours after check-out (review request)'

    name = models.CharField(max_length=100)
    trigger = models.CharField(max_length=30, choices=Trigger.choices)
    # booking_confirmed / after_check_out: olaydan SONRA saat; before_check_in: girişten ÖNCE saat.
    offset_hours = models.PositiveIntegerField(default=0)
    # check_in_day / check_out_morning için gönderim saati (yerel). Boşsa 10:00 / 08:00.
    send_time = models.TimeField(null=True, blank=True)
    language = models.CharField(max_length=10, default='en')
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['trigger', 'language', 'name']

    def __str__(self):
        return f'{self.name} ({self.trigger}, {self.language})'


class ScheduledMessage(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENDING = 'sending', 'Sending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        SKIPPED = 'skipped', 'Skipped (too late)'

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='scheduled_messages')
    template = models.ForeignKey(MessageTemplate, on_delete=models.CASCADE, related_name='scheduled_messages')
    send_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    channel = models.CharField(max_length=20, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['send_at']
        constraints = [
            # Aynı mesaj aynı rezervasyona iki kez planlanamaz / gönderilemez.
            models.UniqueConstraint(fields=['reservation', 'template'], name='unique_message_per_reservation'),
        ]
        indexes = [models.Index(fields=['status', 'send_at'], name='scheduled_due_idx')]


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
        AUTO = 'auto', 'Automatic message'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=3, choices=Direction.choices)
    source = models.CharField(max_length=10, choices=Source.choices)
    body = models.TextField()
    sent_at = models.DateTimeField()
    # Kanal (Beds24) mesaj id'si: aynı mesaj iki kez içe aktarılmaz.
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    is_read = models.BooleanField(default=True)
    scheduled_message = models.OneToOneField(
        ScheduledMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name='message',
    )
    sent_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ['sent_at', 'created_at']
