"""Finans tamamen otomatik: elle girilmiş / görevlerden oluşmuş masraf ve diğer gelir kayıtlarını siler.
Defterde sadece rezervasyonlardan otomatik oluşan gelir kayıtları kalır."""
from django.db import migrations


def forwards(apps, schema_editor):
    FinancialTransaction = apps.get_model('finance', 'FinancialTransaction')
    FinancialTransaction.objects.exclude(category='reservation').delete()


class Migration(migrations.Migration):
    dependencies = [('finance', '0007_remove_recurringexpense_property_and_more')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
