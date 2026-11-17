from django.contrib.auth.models import User
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSummarySerializer


class MeView(APIView):
    """Giriş yapan kullanıcının rolü (frontend temizlikçi görünümüne yönlendirmek için)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSummarySerializer(request.user).data)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Personel listesi (görev/temizlikçi atama dropdown'ları için). ?group=cleaner"""
    serializer_class = UserSummarySerializer
    pagination_class = None
    filterset_fields = []
    search_fields = ['username', 'first_name', 'last_name']

    def get_queryset(self):
        qs = User.objects.filter(is_active=True).prefetch_related('groups').order_by('first_name', 'username')
        group = self.request.query_params.get('group')
        if group:
            qs = qs.filter(groups__name=group)
        return qs
