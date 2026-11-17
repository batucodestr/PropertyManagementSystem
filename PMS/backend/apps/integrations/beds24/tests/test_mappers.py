from datetime import date, datetime, timezone
from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from apps.integrations.beds24 import mappers
from apps.properties.pricing import DayRate, apply_markup, suggested_markup
from .helpers import booking


def day(d, price='100.00', closed=False, min_stay=1):
    return DayRate(date=d, price=Decimal(price), min_stay=min_stay, closed=closed,
                   available=not closed, source='base')


class MapperTests(SimpleTestCase):
    def test_status_mapping(self):
        self.assertEqual(mappers.map_status('new'), 'confirmed')
        self.assertEqual(mappers.map_status('confirmed'), 'confirmed')
        self.assertEqual(mappers.map_status('request'), 'pending')
        self.assertEqual(mappers.map_status('cancelled'), 'cancelled')
        self.assertIsNone(mappers.map_status('inquiry'))
        self.assertIsNone(mappers.map_status('black'))
        self.assertEqual(mappers.map_status('confirmed', 'noShow'), 'no_show')

    def test_source_mapping(self):
        self.assertEqual(mappers.map_source({'channel': 'airbnb'}), 'airbnb')
        self.assertEqual(mappers.map_source({'channel': 'booking'}), 'booking')
        self.assertEqual(mappers.map_source({'channel': 'expedia'}), 'other')
        self.assertEqual(mappers.map_source({'channel': None, 'apiSource': ''}), 'direct')
        self.assertEqual(mappers.map_source({'channel': '', 'apiSource': 'Booking.com'}), 'booking')

    @override_settings(PROPERTY_TIMEZONE='Europe/Istanbul', DEFAULT_CHECKIN_TIME='15:00',
                       DEFAULT_CHECKOUT_TIME='11:00')
    def test_booking_dates_use_property_timezone(self):
        check_in, check_out = mappers.booking_dates({'arrival': '2030-07-01', 'departure': '2030-07-05'})
        self.assertEqual(check_in.astimezone(timezone.utc), datetime(2030, 7, 1, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(check_out.astimezone(timezone.utc), datetime(2030, 7, 5, 8, 0, tzinfo=timezone.utc))

    def test_reservation_fields_use_decimal(self):
        fields = mappers.reservation_fields(booking())
        self.assertEqual(fields['total_price'], Decimal('4800.50'))
        self.assertIsInstance(fields['total_price'], Decimal)
        self.assertEqual(fields['source'], 'airbnb')
        self.assertEqual(fields['external_source_id'], '77700001')
        self.assertEqual(fields['channel_booking_ref'], 'HMABC12345')
        self.assertEqual((fields['adults'], fields['children']), (2, 1))

    def test_zero_adults_become_one(self):
        self.assertEqual(mappers.reservation_fields(booking(numAdult=0))['adults'], 1)

    def test_calendar_entries_merge_identical_consecutive_days(self):
        days = [
            day(date(2030, 1, 1)), day(date(2030, 1, 2)), day(date(2030, 1, 3), price='150.00'),
            day(date(2030, 1, 4), price='150.00', closed=True), day(date(2030, 1, 5), price='150.00', closed=True),
        ]
        entries = mappers.calendar_entries(days)
        self.assertEqual([(e['from'], e['to']) for e in entries], [
            ('2030-01-01', '2030-01-02'), ('2030-01-03', '2030-01-03'), ('2030-01-04', '2030-01-05'),
        ])
        self.assertEqual(entries[2]['override'], 'blackout')
        self.assertEqual(entries[0]['override'], 'none')
        self.assertNotIn('numAvail', entries[0])

    def test_calendar_entries_apply_channel_markups(self):
        entry = mappers.calendar_entries([day(date(2030, 1, 1))], Decimal('18.34'), Decimal('10'))[0]
        self.assertEqual(entry['price1'], 100.0)
        self.assertEqual(entry['price2'], 118.34)
        self.assertEqual(entry['price3'], 110.0)

    def test_markup_math(self):
        self.assertEqual(suggested_markup(Decimal('15.5')), Decimal('18.34'))
        self.assertEqual(apply_markup(Decimal('99.99'), Decimal('18.34')), Decimal('118.33'))
        self.assertEqual(apply_markup(Decimal('100.005'), 0), Decimal('100.01'))  # ROUND_HALF_UP

    def test_new_id_from_post(self):
        self.assertEqual(mappers.new_id_from_post([{'success': True, 'new': {'id': 5}}]), '5')
        self.assertIsNone(mappers.new_id_from_post([{'success': True, 'modified': {'id': 5}}]))
