from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.properties.pricing import property_tz
from .models import GeneralTask, HouseKeepingTasks, TaskPhoto
from .serializers import (
    CleanerTaskSerializer, GeneralTaskSerializer, HouseKeepingTasksSerializer, TaskPhotoSerializer,
)


class HouseKeepingTasksViewSet(viewsets.ModelViewSet):
    queryset = (
        HouseKeepingTasks.objects.select_related('property', 'reservation', 'assigned_to')
        .prefetch_related('photos').order_by('-scheduled_date', 'id')
    )
    serializer_class = HouseKeepingTasksSerializer
    filterset_fields = {
        'property': ['exact'],
        'reservation': ['exact'],
        'assigned_to': ['exact'],
        'status': ['exact'],
        'priority': ['exact'],
        'is_auto': ['exact'],
        'scheduled_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['notes', 'property__name']
    ordering_fields = ['scheduled_date', 'status', 'priority', 'created_at']


class GeneralTaskViewSet(viewsets.ModelViewSet):
    queryset = (
        GeneralTask.objects.select_related('property', 'availability_block')
        .prefetch_related('photos').order_by('due_date', 'id')
    )
    serializer_class = GeneralTaskSerializer
    filterset_fields = {
        'property': ['exact'],
        'assigned_to': ['exact'],
        'status': ['exact', 'in'],
        'task_type': ['exact'],
        'priority': ['exact'],
        'due_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['description', 'property__name']
    ordering_fields = ['due_date', 'status', 'priority', 'created_at']


class TaskPhotoViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin,
                       viewsets.GenericViewSet):
    queryset = TaskPhoto.objects.order_by('created_at')
    serializer_class = TaskPhotoSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ['general_task', 'housekeeping_task']

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def perform_destroy(self, instance):
        instance.image.delete(save=False)
        instance.delete()


class CleanerTaskViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Temizlikçi görünümü: sadece kendisine atanmış bugünkü/yarınki (ve süren/geciken) görevler."""
    serializer_class = CleanerTaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = []
    search_fields = []

    def get_queryset(self):
        today = timezone.localdate(timezone=property_tz())
        return (
            HouseKeepingTasks.objects.filter(assigned_to=self.request.user)
            .filter(
                Q(scheduled_date__in=(today, today + timedelta(days=1)))
                | Q(status=HouseKeepingTasks.Status.IN_PROGRESS)
                | Q(status=HouseKeepingTasks.Status.PENDING, scheduled_date__lt=today)
            )
            .select_related('property').prefetch_related('photos')
            .order_by('scheduled_date', '-priority', 'id')
        )

    def _respond(self, task):
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        with transaction.atomic():
            task = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
            if task.status == HouseKeepingTasks.Status.COMPLETED:
                return Response({'detail': 'Task is already completed.'}, status=status.HTTP_409_CONFLICT)
            task.status = HouseKeepingTasks.Status.IN_PROGRESS
            task.started_at = task.started_at or timezone.now()
            task.save(update_fields=['status', 'started_at', 'updated_at'])
        return self._respond(task)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        with transaction.atomic():
            task = get_object_or_404(self.get_queryset().select_for_update(of=('self',)), pk=pk)
            task.status = HouseKeepingTasks.Status.COMPLETED
            task.completed_date = timezone.localdate(timezone=property_tz())
            task.started_at = task.started_at or timezone.now()
            notes = request.data.get('notes')
            if notes is not None:
                task.notes = str(notes)[:2000]
            task.save()
        return self._respond(task)

    @action(detail=True, methods=['post'])
    def notes(self, request, pk=None):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        task.notes = str(request.data.get('notes', ''))[:2000]
        task.save(update_fields=['notes', 'updated_at'])
        return self._respond(task)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        task = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = TaskPhotoSerializer(data={
            'housekeeping_task': task.pk, 'image': request.data.get('image'),
            'caption': request.data.get('caption', ''),
        })
        serializer.is_valid(raise_exception=True)
        serializer.save(uploaded_by=request.user)
        task.refresh_from_db()
        return Response(self.get_serializer(task).data, status=status.HTTP_201_CREATED)
