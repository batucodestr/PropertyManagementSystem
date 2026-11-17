from django.db import models
from apps.core.models import BaseModel

class Property(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    max_guests = models.PositiveIntegerField()
    bedroom_count = models.PositiveIntegerField()
    bed_count = models.PositiveIntegerField()
    bathroom_count = models.PositiveIntegerField()
    area = models.DecimalField(max_digits=10, decimal_places=2)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class HousekeepingStatus(models.TextChoices):
        READY = 'ready', 'Ready'
        DIRTY = 'dirty', 'Needs cleaning'
        CLEANING = 'cleaning', 'Cleaning in progress'

    housekeeping_status = models.CharField(
        max_length=10, choices=HousekeepingStatus.choices, default=HousekeepingStatus.READY,
    )

    def __str__(self):
        return self.name


def property_image_upload_to(instance, filename):
    return f'property_images/{instance.property.id}/{filename}'

class PropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=property_image_upload_to)
    alt_text = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Image for {self.property.name}"


class SeasonalRate(BaseModel):
    """Tarih aralığına göre gecelik fiyat (bitiş günü dahil)."""
    property = models.ForeignKey(Property, related_name='seasonal_rates', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    nightly_price = models.DecimalField(max_digits=10, decimal_places=2)
    weekend_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_stay = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['start_date', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')),
                name='seasonal_rate_end_not_before_start',
            ),
            models.CheckConstraint(condition=models.Q(nightly_price__gte=0), name='seasonal_rate_price_non_negative'),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.name}"


class DailyRate(BaseModel):
    """Gün bazlı manuel override (fiyat, min stay, kapalı)."""
    property = models.ForeignKey(Property, related_name='daily_rates', on_delete=models.CASCADE)
    date = models.DateField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_stay = models.PositiveIntegerField(null=True, blank=True)
    closed = models.BooleanField(default=False)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['property', 'date'], name='unique_daily_rate'),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.date}"


