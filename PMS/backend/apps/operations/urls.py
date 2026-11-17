from rest_framework.routers import SimpleRouter

from .views import CleanerTaskViewSet, GeneralTaskViewSet, HouseKeepingTasksViewSet, TaskPhotoViewSet

router = SimpleRouter()
router.register('housekeeping', HouseKeepingTasksViewSet, basename='housekeeping')
router.register('general-tasks', GeneralTaskViewSet, basename='general-task')
router.register('task-photos', TaskPhotoViewSet, basename='task-photo')
# Temizlikçi (mobil) görünümü: sadece kendi görevleri.
router.register('cleaner/tasks', CleanerTaskViewSet, basename='cleaner-task')

urlpatterns = router.urls
