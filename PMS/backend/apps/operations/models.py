import uuid

from django.db import models
from apps.core.models import BaseModel
from apps.reservations.models import AvailabilityBlock, Reservation
from apps.properties.models import Property

# Create your models here.


class GeneralTask(BaseModel):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    class TaskType(models.TextChoices):
        GENERAL = 'general', 'General'
        MAINTENANCE = 'maintenance', 'Maintenance'
        INSPECTION = 'inspection', 'Inspection'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='general_tasks'
    )
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.GENERAL)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    # Kritik arızada evin takvimini kapatan blok (kanal senkronu bunu satışa kapatır).
    availability_block = models.OneToOneField(
        AvailabilityBlock, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_task',
    )
    description = models.TextField(null=False, blank=False)
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    due_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    # Tamamlandığında girilirse masraf (FinancialTransaction) olarak kaydedilir.
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    def __str__(self):
        return f"{self.property.name} - {self.description[:20]}"


class HouseKeepingTasks(BaseModel):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        URGENT = 'urgent', 'Urgent (same-day check-in)'

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='housekeeping_tasks'
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    # Rezervasyondan otomatik oluşturulan check-out temizliği (rezervasyon başına tek).
    is_auto = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='housekeeping_tasks',
        null=True,
        blank=True,
    )
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # Tamamlandığında girilirse temizlik masrafı olarak kaydedilir.
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['reservation'], condition=models.Q(is_auto=True),
                name='unique_auto_housekeeping_per_reservation',
            ),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.status}"


def task_photo_upload_to(instance, filename):
    # Medya kimlik doğrulamasız servis edilir: yol tahmin edilemez olsun.
    return f"task_photos/{uuid.uuid4().hex}/{filename}"


class TaskPhoto(BaseModel):
    """Temizlik veya bakım görevine eklenen fotoğraf."""
    general_task = models.ForeignKey(
        GeneralTask, on_delete=models.CASCADE, null=True, blank=True, related_name='photos',
    )
    housekeeping_task = models.ForeignKey(
        HouseKeepingTasks, on_delete=models.CASCADE, null=True, blank=True, related_name='photos',
    )
    image = models.ImageField(upload_to=task_photo_upload_to, max_length=255)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(general_task__isnull=False, housekeeping_task__isnull=True)
                    | models.Q(general_task__isnull=True, housekeeping_task__isnull=False)
                ),
                name='task_photo_exactly_one_task',
            ),
        ]


class StayRecord(BaseModel):
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name="stay_record"
    )
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="check_ins"
    )
    checked_out_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="check_outs"
    )
    notes = models.TextField(blank=True)
