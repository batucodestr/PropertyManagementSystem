from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.integrations.beds24.client import Beds24Client, Beds24Error


class Command(BaseCommand):
    help = "Beds24 bağlantısını test eder: token alır, GET /properties çağırır, ev sayısını yazar."

    def handle(self, *args, **options):
        client = Beds24Client()
        try:
            client.get_token(force_refresh=True)
            properties = client.get_all('/properties', action='ping')
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc))
        except Beds24Error as exc:
            raise CommandError(f'Beds24 hatası: {exc}')
        self.stdout.write(self.style.SUCCESS(f'Beds24 bağlantısı OK. Ev (property) sayısı: {len(properties)}'))
        for prop in properties:
            rooms = ', '.join(f"{r.get('id')}:{r.get('name')}" for r in prop.get('roomTypes') or [])
            self.stdout.write(f"  - {prop.get('id')}  {prop.get('name')}  [odalar: {rooms or '-'}]")
