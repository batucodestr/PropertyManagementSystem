from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.integrations.beds24 import services
from apps.integrations.beds24.client import Beds24Error
from apps.properties.models import Property


class Command(BaseCommand):
    help = "Var olan bir Beds24 property'sini PMS evine bağlar ve senkronlar."

    def add_arguments(self, parser):
        parser.add_argument('pms_property_id', help='PMS Property UUID')
        parser.add_argument('beds24_property_id', type=int, help='Beds24 propertyId')
        parser.add_argument('--no-sync', action='store_true', help='Sadece eşle, Beds24 verisini güncelleme')

    def handle(self, pms_property_id, beds24_property_id, no_sync=False, **options):
        prop = Property.objects.filter(pk=pms_property_id).first()
        if prop is None:
            raise CommandError(f'PMS evi bulunamadı: {pms_property_id}')
        try:
            listing = services.link_property(prop, beds24_property_id)
            self.stdout.write(f'Eşlendi: {prop.name} -> Beds24 property {listing.external_listing_id}, '
                              f'room {listing.external_room_id}')
            if not no_sync:
                services.sync_property(prop)
                self.stdout.write(self.style.SUCCESS('Senkron tamam (ev bilgileri + 365 günlük takvim).'))
        except (Beds24Error, ImproperlyConfigured) as exc:
            raise CommandError(str(exc))
