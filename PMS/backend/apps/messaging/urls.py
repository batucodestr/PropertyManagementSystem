from rest_framework.routers import SimpleRouter

from .views import ConversationViewSet, MessageTemplateViewSet, ScheduledMessageViewSet

router = SimpleRouter()
router.register('templates', MessageTemplateViewSet, basename='message-template')
router.register('scheduled', ScheduledMessageViewSet, basename='scheduled-message')
router.register('conversations', ConversationViewSet, basename='conversation')

urlpatterns = router.urls
