from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.reservations.models import AvailabilityBlock
from .models import GeneralTask, HouseKeepingTasks, StayRecord, TaskPhoto

MAX_PHOTO_BYTES = 10 * 1024 * 1024


class TaskPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPhoto
        fields = ['id', 'general_task', 'housekeeping_task', 'image', 'caption', 'uploaded_by', 'created_at']
        read_only_fields = ['id', 'uploaded_by', 'created_at']

    def validate_image(self, value):
        if value.size > MAX_PHOTO_BYTES:
            raise serializers.ValidationError("Photo must be 10 MB or smaller.")
        return value

    def validate(self, data):
        if bool(data.get('general_task')) == bool(data.get('housekeeping_task')):
            raise serializers.ValidationError("Attach the photo to exactly one task.")
        return data


def sync_completed_date(data):
    """Keep completed_date consistent with status when status is being written."""
    if 'status' not in data:
        return
    if data['status'] == 'completed':
        if not data.get('completed_date'):
            data['completed_date'] = timezone.localdate()
    else:
        data['completed_date'] = None

class GeneralTaskSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    photos = TaskPhotoSerializer(many=True, read_only=True)
    # Kritik arızada takvimi bu tarihe kadar (dahil) kapat; null = bloğu kaldır.
    close_calendar_until = serializers.DateField(write_only=True, required=False, allow_null=True)
    calendar_closed_until = serializers.DateField(source='availability_block.end_date', read_only=True, default=None)

    class Meta:
        model = GeneralTask
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'availability_block']

    def validate_status(self, value):
        if value not in [choice[0] for choice in GeneralTask.Status.choices]:
            raise serializers.ValidationError("Invalid status.")
        return value

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Description cannot be empty.")
        return value

    def validate(self, data):
        sync_completed_date(data)
        if data.get('cost') is not None and data['cost'] < 0:
            raise serializers.ValidationError({"cost": "Cost cannot be negative."})
        until = data.get('close_calendar_until')
        if until and until < timezone.localdate():
            raise serializers.ValidationError({"close_calendar_until": "Date cannot be in the past."})
        return data

    def _apply_block(self, task, until, provided):
        """Takvim bloğunu oluştur / uzat / kaldır (kanal senkronu blok sinyalleriyle tetiklenir)."""
        if not provided:
            return
        block = task.availability_block
        if until and task.status != GeneralTask.Status.COMPLETED:
            reason = f"Maintenance: {task.description[:200]}"
            if block:
                block.end_date, block.reason = until, reason
                block.save()
            else:
                start = timezone.localdate()
                block = AvailabilityBlock.objects.filter(property=task.property, start_date=start, end_date=until).first()                     or AvailabilityBlock.objects.create(property=task.property, start_date=start, end_date=until, reason=reason)
                GeneralTask.objects.filter(pk=task.pk).update(availability_block=block)
                task.availability_block = block
        elif block:
            GeneralTask.objects.filter(pk=task.pk).update(availability_block=None)
            task.availability_block = None
            block.delete()

    def create(self, validated_data):
        provided = 'close_calendar_until' in validated_data
        until = validated_data.pop('close_calendar_until', None)
        with transaction.atomic():
            task = super().create(validated_data)
            self._apply_block(task, until, provided)
        return task

    def update(self, instance, validated_data):
        provided = 'close_calendar_until' in validated_data
        until = validated_data.pop('close_calendar_until', None)
        with transaction.atomic():
            task = super().update(instance, validated_data)
            self._apply_block(task, until, provided)
        return task

class HouseKeepingTasksSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    photos = TaskPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = HouseKeepingTasks
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_auto', 'started_at']

    def get_assigned_to_name(self, obj):
        user = obj.assigned_to
        return (user.get_full_name() or user.username) if user else None

    def validate_status(self, value):
        if value not in [choice[0] for choice in HouseKeepingTasks.Status.choices]:
            raise serializers.ValidationError("Invalid status.")
        return value

    def validate(self, data):
        prop = data.get('property', getattr(self.instance, 'property', None))
        reservation = data.get('reservation', getattr(self.instance, 'reservation', None))
        if prop and reservation and reservation.property_id != prop.pk:
            raise serializers.ValidationError(
                {"reservation": "Reservation does not belong to the selected property."}
            )
        sync_completed_date(data)
        return data


class StayRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = StayRecord
        fields = ['id', 'reservation', 'actual_check_in', 'actual_check_out',
                  'checked_in_by', 'checked_out_by', 'notes', 'created_at', 'updated_at']
        read_only_fields = fields


class CleanerTaskSerializer(serializers.ModelSerializer):
    """Temizlikçi görünümü: sadece işini yapması için gereken bilgi (misafir kişisel verisi yok)."""
    property_name = serializers.CharField(source='property.name', read_only=True)
    property_address = serializers.SerializerMethodField()
    next_check_in = serializers.SerializerMethodField()
    photos = TaskPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = HouseKeepingTasks
        fields = [
            'id', 'property', 'property_name', 'property_address', 'scheduled_date', 'priority', 'status',
            'started_at', 'completed_date', 'notes', 'next_check_in', 'photos',
        ]
        read_only_fields = fields

    def get_property_address(self, obj):
        p = obj.property
        return ', '.join(x for x in (p.address, p.city) if x)

    def get_next_check_in(self, obj):
        from apps.reservations.models import Reservation

        nxt = (
            Reservation.objects.filter(
                property_id=obj.property_id, status__in=('pending', 'confirmed'),
                check_in__date__gte=obj.scheduled_date,
            ).order_by('check_in').values('check_in', 'adults', 'children').first()
        )
        if not nxt:
            return None
        return {'check_in': nxt['check_in'], 'guests': nxt['adults'] + nxt['children']}
