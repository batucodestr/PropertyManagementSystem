from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import override_settings

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.properties import pricing
from apps.properties.models import DailyRate, SeasonalRate
from apps.reservations.models import AvailabilityBlock, Reservation

IST = ZoneInfo('Europe/Istanbul')


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul', WEEKEND_NIGHTS=[4, 5])
class PricingTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property(base_price=Decimal('100.00'))
        # 2030-07-01 Pazartesi
        self.mon = date(2030, 7, 1)

    def by_date(self, start, end):
        return {d.date: d for d in pricing.calendar(self.prop, start, end)}

    def test_priority_daily_over_seasonal_over_base(self):
        SeasonalRate.objects.create(property=self.prop, name='Summer', start_date=self.mon,
                                    end_date=self.mon + timedelta(days=6), nightly_price=Decimal('150'),
                                    weekend_price=Decimal('180'), min_stay=3)
        DailyRate.objects.create(property=self.prop, date=self.mon + timedelta(days=1), price=Decimal('300'))
        days = self.by_date(self.mon, self.mon + timedelta(days=7))
        self.assertEqual((days[self.mon].price, days[self.mon].source), (Decimal('150.00'), 'seasonal'))
        self.assertEqual(days[self.mon].min_stay, 3)
        self.assertEqual((days[self.mon + timedelta(days=1)].price, days[self.mon + timedelta(days=1)].source),
                         (Decimal('300.00'), 'daily'))
        friday, saturday, sunday = (self.mon + timedelta(days=n) for n in (4, 5, 6))
        self.assertEqual(days[friday].price, Decimal('180.00'))
        self.assertEqual(days[saturday].source, 'weekend')
        self.assertEqual(days[sunday].price, Decimal('150.00'))
        self.assertEqual((days[self.mon + timedelta(days=7)].price, days[self.mon + timedelta(days=7)].source),
                         (Decimal('100.00'), 'base'))

    def test_availability_reservations_blocks_and_closed(self):
        Reservation.objects.create(
            property=self.prop, guest=make_guest(), status='confirmed', total_price=Decimal('200'),
            check_in=datetime(2030, 7, 1, 15, tzinfo=IST), check_out=datetime(2030, 7, 3, 11, tzinfo=IST),
        )
        Reservation.objects.create(
            property=self.prop, guest=make_guest(email='x@example.com'), status='cancelled',
            total_price=Decimal('200'),
            check_in=datetime(2030, 7, 3, 15, tzinfo=IST), check_out=datetime(2030, 7, 4, 11, tzinfo=IST),
        )
        AvailabilityBlock.objects.create(property=self.prop, start_date=date(2030, 7, 4), end_date=date(2030, 7, 4))
        DailyRate.objects.create(property=self.prop, date=date(2030, 7, 5), closed=True)
        days = self.by_date(self.mon, self.mon + timedelta(days=5))
        self.assertEqual([days[self.mon + timedelta(days=n)].reason for n in range(6)],
                         ['reservation', 'reservation', '', 'block', 'closed', ''])
        self.assertFalse(days[self.mon].closed)   # rezervasyon gecesi kanallarda Beds24'ün kendisince kapanır
        self.assertTrue(days[date(2030, 7, 4)].closed)
        self.assertTrue(days[date(2030, 7, 3)].available)

    def test_rates_endpoint(self):
        response = self.client.get(f'/api/properties/{self.prop.pk}/rates/', {'from': '2030-07-01', 'to': '2030-07-03'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['days']), 3)
        self.assertEqual(data['days'][0], {
            'date': '2030-07-01', 'price': '100.00', 'min_stay': 1, 'closed': False,
            'available': True, 'source': 'base', 'reason': '',
        })

    def test_rates_endpoint_validates_range(self):
        url = f'/api/properties/{self.prop.pk}/rates/'
        self.assertEqual(self.client.get(url, {'from': '2030-07-05', 'to': '2030-07-01'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'from': 'bad'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'from': '2030-01-01', 'to': '2031-12-31'}).status_code, 400)

    def test_bulk_set_and_clear(self):
        url = f'/api/properties/{self.prop.pk}/rates/bulk/'
        response = self.client.post(url, {'date_from': '2030-07-01', 'date_to': '2030-07-03',
                                          'price': '120.00', 'min_stay': 2}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyRate.objects.filter(property=self.prop, price=Decimal('120')).count(), 3)
        self.client.post(url, {'date_from': '2030-07-02', 'date_to': '2030-07-02', 'closed': True}, format='json')
        rate = DailyRate.objects.get(property=self.prop, date=date(2030, 7, 2))
        self.assertTrue(rate.closed)
        self.assertEqual(rate.price, Decimal('120.00'))  # gönderilmeyen alan korunur
        self.client.post(url, {'date_from': '2030-07-01', 'date_to': '2030-07-03', 'clear': True}, format='json')
        self.assertFalse(DailyRate.objects.filter(property=self.prop).exists())

    def test_seasonal_rate_crud_validation(self):
        response = self.client.post('/api/seasonal-rates/', {
            'property': str(self.prop.pk), 'name': 'Bad', 'start_date': '2030-07-05', 'end_date': '2030-07-01',
            'nightly_price': '100',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/seasonal-rates/', {
            'property': str(self.prop.pk), 'name': 'Summer', 'start_date': '2030-07-01', 'end_date': '2030-08-31',
            'nightly_price': '150', 'weekend_price': '180',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get('/api/seasonal-rates/', {'property': str(self.prop.pk)}).json()['count'], 1)
