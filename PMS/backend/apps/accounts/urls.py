from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView, TokenBlacklistView

from .views import MeView, UserViewSet

router = SimpleRouter()
router.register('users', UserViewSet, basename='user')

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('token/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('me/', MeView.as_view(), name='me'),
    *router.urls,
]
