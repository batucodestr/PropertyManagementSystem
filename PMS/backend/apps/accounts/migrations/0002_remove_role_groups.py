"""Temizlikçi/yönetici rol ayrımı kaldırıldı: 0001'de oluşturulan grupları siler."""
from django.db import migrations

ROLE_GROUPS = ('cleaner', 'manager')


def remove_groups(apps, schema_editor):
    apps.get_model('auth', 'Group').objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_create_role_groups')]
    operations = [migrations.RunPython(remove_groups, migrations.RunPython.noop)]
