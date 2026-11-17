"""Basit rol ayrımı (Django grupları).

- cleaner: sadece kendisine atanmış temizlik görevlerini görür/günceller (temizlikçi görünümü).
- manager: tam yönetim paneli erişimi (grupsuz personel ve superuser da tam erişimlidir).
Bir kullanıcı hem cleaner hem manager ise manager sayılır.
"""
CLEANER = 'cleaner'
MANAGER = 'manager'


def group_names(user):
    if not user or not user.is_authenticated:
        return set()
    cached = getattr(user, '_group_names', None)
    if cached is None:
        cached = set(user.groups.values_list('name', flat=True))
        user._group_names = cached
    return cached


def is_cleaner_only(user):
    """Sadece temizlikçi (yönetim paneline erişimi yok)."""
    if not user or not user.is_authenticated or user.is_superuser:
        return False
    names = group_names(user)
    return CLEANER in names and MANAGER not in names


def role_of(user):
    if is_cleaner_only(user):
        return CLEANER
    return MANAGER
