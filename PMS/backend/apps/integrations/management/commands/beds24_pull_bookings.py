from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.integrations.beds24 import services
from apps.integrations.beds24.client import Beds24Error


class Command(BaseCommand):
    help = "Beds24'te değişen rezervasyonları çeker (polling'in elle çalıştırılması)."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None,
                            help='Son N günde değişenleri çek (varsayılan: son polling\'den beri)')

    def handle(self, days=None, **options):
        since = timezone.now() - timedelta(days=days) if days else None
        try:
            summary = services.pull_bookings(modified_from=since)
        except (Beds24Error, ImproperlyConfigured) as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'Tamam: {summary or "bağlı ev yok"}'))
