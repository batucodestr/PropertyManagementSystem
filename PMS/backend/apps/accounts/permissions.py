from rest_framework.permissions import BasePermission

from .roles import is_cleaner_only


class IsStaffMember(BasePermission):
    """Varsayılan izin: giriş yapmış ve sadece-temizlikçi olmayan kullanıcı (yönetim paneli)."""
    message = 'Cleaners can only access their own housekeeping tasks.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not is_cleaner_only(user))
