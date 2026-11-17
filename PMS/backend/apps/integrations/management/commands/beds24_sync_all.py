from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.integrations.beds24 import services
from apps.integrations.beds24.client import Beds24Error
from apps.properties.models import Property


class Command(BaseCommand):
    help = "Tüm PMS evlerini Beds24'e senkronlar (eşleme yoksa oluşturur) ve takvimleri gönderir."

    def add_arguments(self, parser):
        parser.add_argument('--active-only', action='store_true', help='Sadece aktif evler')

    def handle(self, active_only=False, **options):
        qs = Property.objects.order_by('name')
        if active_only:
            qs = qs.filter(is_active=True)
        failed = 0
        for prop in qs:
            try:
                listing = services.sync_property(prop)
                self.stdout.write(self.style.SUCCESS(f'OK  {prop.name} -> {listing.external_listing_id}'))
            except ImproperlyConfigured as exc:
                raise CommandError(str(exc))
            except Beds24Error as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f'HATA {prop.name}: {exc}'))
        if failed:
            raise CommandError(f'{failed} ev senkronlanamadı (ayrıntı: Sync Log).')
