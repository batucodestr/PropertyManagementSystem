from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property

class ChannelConnection(BaseModel):
    provider = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    credentials = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

class ChannelListing(BaseModel):
    """Bir PMS evinin kanal yöneticisindeki (Beds24) karşılığı.

    Beds24: external_listing_id = propertyId, external_room_id = roomTypeId (qty=1).
    """

    class SyncStatus(models.TextChoices):
        OK = "ok", "OK"
        PENDING = "pending", "Pending"
        ERROR = "error", "Error"

    connection = models.ForeignKey(
        ChannelConnection,
        on_delete=models.CASCADE,
        related_name="listings"
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="channel_listings"
    )
    external_listing_id = models.CharField(max_length=255)
    external_room_id = models.CharField(max_length=255, blank=True)
    external_url = models.URLField(blank=True)
    sync_enabled = models.BooleanField(default=True)
    sync_status = models.CharField(
        max_length=10, choices=SyncStatus.choices, default=SyncStatus.PENDING
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    # Kanal komisyonunu telafi eden fiyat artışı (%). Örn. Airbnb %15,5 komisyon -> ~%18,34.
    airbnb_markup_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    booking_markup_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Beds24 API V2 OTA bağlantı durumunu güvenilir şekilde vermediği için elle işaretlenir.
    airbnb_connected = models.BooleanField(default=False)
    booking_connected = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_listing_id"],
                name="unique_external_listing"
            ),
            models.UniqueConstraint(
                fields=["connection", "property"],
                name="unique_listing_per_property"
            ),
        ]

    def __str__(self):
        return f"{self.property} -> {self.connection.provider}:{self.external_listing_id}"


class SyncLog(BaseModel):
    connection = models.ForeignKey(
        ChannelConnection,
        on_delete=models.CASCADE,
        related_name="sync_logs"
    )
    action = models.CharField(max_length=100)
    status = models.CharField(max_length=30)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=["-created_at"], name="synclog_created_idx")]


class WebhookEvent(BaseModel):
    provider = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
