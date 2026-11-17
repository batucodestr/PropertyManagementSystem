import os
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import responses
from django.test import override_settings
from django.utils import timezone

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.integrations.beds24.client import get_connection
from apps.integrations.models import ChannelListing, SyncLog
from apps.properties.models import DailyRate, SeasonalRate
from apps.reservations.models import AvailabilityBlock, Reservation
from .helpers import API, Beds24TestMixin, fixture


class ChannelApiTests(Beds24TestMixin, AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        self.unlinked = make_property(name='Unlinked')
        self.listing = ChannelListing.objects.create(
            connection=get_connection(), property=self.prop, external_listing_id='250001',
            external_room_id='560001', sync_status='ok', airbnb_connected=True,
        )

    def test_channel_overview(self):
        response = self.client.get('/api/integrations/channels/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['configured'])
        self.assertFalse(data['photos_supported'])
        self.assertEqual(data['suggested_markup']['airbnb'], '18.34')
        rows = {r['property']['name']: r for r in data['results']}
        self.assertEqual(rows['Sea View']['listing']['external_listing_id'], '250001')
        self.assertTrue(rows['Sea View']['listing']['airbnb_connected'])
        self.assertIsNone(rows['Unlinked']['listing'])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/integrations/channels/').status_code, 401)
        self.assertEqual(self.client.get('/api/integrations/sync-logs/').status_code, 401)

    def test_patch_listing_markups_and_flags_only(self):
        response = self.client.patch(f'/api/integrations/listings/{self.listing.pk}/', {
            'airbnb_markup_percent': '18.34', 'booking_connected': True, 'external_listing_id': 'hack',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.airbnb_markup_percent, Decimal('18.34'))
        self.assertTrue(self.listing.booking_connected)
        self.assertEqual(self.listing.external_listing_id, '250001')

    def test_markup_validation(self):
        response = self.client.patch(f'/api/integrations/listings/{self.listing.pk}/',
                                     {'airbnb_markup_percent': '150'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_manual_sync(self):
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('properties_post_modified.json'))
        self.rsps.add(responses.POST, f'{API}/inventory/rooms/calendar', json=fixture('calendar_post.json'))
        response = self.client.post(f'/api/integrations/properties/{self.prop.pk}/sync/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sync_status'], 'ok')

    def test_manual_sync_reports_beds24_error(self):
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('post_error.json'))
        response = self.client.post(f'/api/integrations/properties/{self.prop.pk}/sync/')
        self.assertEqual(response.status_code, 502)
        self.assertIn('invalid roomId', response.json()['detail'])

    def test_manual_sync_without_token_is_503(self):
        with mock.patch.dict(os.environ, {'BEDS24_REFRESH_TOKEN': ''}):
            response = self.client.post(f'/api/integrations/properties/{self.prop.pk}/sync/')
        self.assertEqual(response.status_code, 503)
        self.assertIn('BEDS24_REFRESH_TOKEN', response.json()['detail'])

    def test_sync_logs_are_filterable_and_paginated(self):
        conn = get_connection()
        SyncLog.objects.create(connection=conn, action='rates.push', status='success', message='ok')
        SyncLog.objects.create(connection=conn, action='booking.poll', status='error', message='fail')
        response = self.client.get('/api/integrations/sync-logs/', {'status': 'error'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['action'], 'booking.poll')
        response = self.client.get('/api/integrations/sync-logs/', {'action': 'rates'})
        self.assertEqual(response.json()['count'], 1)

    def test_reservation_channel_fields_are_read_only(self):
        start = timezone.now() + timedelta(days=10)
        response = self.client.post('/api/reservations/', {
            'property': str(self.prop.pk), 'guest': str(make_guest().pk),
            'check_in': start.isoformat(), 'check_out': (start + timedelta(days=2)).isoformat(),
            'adults': 1, 'children': 0, 'total_price': '200.00', 'external_source_id': '123',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Reservation.objects.get().external_source_id, '')


@override_settings(BEDS24_AUTO_SYNC=True)
class SignalTests(AuthenticatedAPITestCase):
    """Kaydetme sonrası task'lar commit'ten sonra kuyruğa atılır; dış API çağrısı yapılmaz."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch('celery.app.task.Task.delay')
        self.delay = patcher.start()
        self.addCleanup(patcher.stop)

    def _queued(self):
        return [(c.args, c.kwargs) for c in self.delay.call_args_list]

    def test_property_create_queues_sync(self):
        with self.captureOnCommitCallbacks(execute=True):
            prop = make_property()
        self.assertIn(((str(prop.pk),), {}), self._queued())

    def test_rate_and_block_changes_queue_rate_push(self):
        prop = make_property()
        today = timezone.localdate()
        self.delay.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            SeasonalRate.objects.create(property=prop, name='Summer', start_date=today,
                                        end_date=today + timedelta(days=5), nightly_price=Decimal('150'))
            DailyRate.objects.create(property=prop, date=today, price=Decimal('180'))
            AvailabilityBlock.objects.create(property=prop, start_date=today, end_date=today)
        self.assertEqual(self.delay.call_count, 3)
        self.assertEqual(self.delay.call_args_list[0].args,
                         (str(prop.pk), today.isoformat(), (today + timedelta(days=5)).isoformat()))

    def test_pms_reservations_are_pushed_but_channel_imports_are_not(self):
        prop = make_property()
        guest = make_guest()
        self.delay.reset_mock()
        start = timezone.now() + timedelta(days=5)
        with self.captureOnCommitCallbacks(execute=True):
            direct = Reservation.objects.create(property=prop, guest=guest, check_in=start,
                                                check_out=start + timedelta(days=2), total_price=Decimal('10'))
            # PMS'e elle girilen Airbnb rezervasyonu da Beds24'e gitmeli (diğer kanallarda tarih kapansın).
            manual_airbnb = Reservation.objects.create(
                property=prop, guest=guest, check_in=start + timedelta(days=10),
                check_out=start + timedelta(days=12), total_price=Decimal('10'), source='airbnb')
            imported = Reservation(property=prop, guest=guest, check_in=start + timedelta(days=20),
                                   check_out=start + timedelta(days=22), total_price=Decimal('10'))
            imported._from_channel = True
            imported.save()
            from_beds24 = Reservation.objects.create(
                property=prop, guest=guest, check_in=start + timedelta(days=30),
                check_out=start + timedelta(days=32), total_price=Decimal('10'), source='airbnb',
                external_source_id='123', created_via_channel=True)
            from_beds24.status = 'confirmed'
            from_beds24.save()  # PMS'te düzenlense de Beds24'e geri yazılmaz
        self.assertEqual(self._queued(), [((str(direct.pk),), {}), ((str(manual_airbnb.pk),), {})])

    def test_deleting_pms_reservation_deletes_beds24_booking_but_not_channel_ones(self):
        prop = make_property()
        guest = make_guest()
        start = timezone.now() + timedelta(days=5)
        pms = Reservation.objects.create(property=prop, guest=guest, check_in=start, check_out=start + timedelta(days=2),
                                         total_price=Decimal('10'), external_source_id='111')
        ota = Reservation.objects.create(property=prop, guest=guest, check_in=start + timedelta(days=5),
                                         check_out=start + timedelta(days=7), total_price=Decimal('10'),
                                         source='airbnb', external_source_id='222', created_via_channel=True)
        local_only = Reservation.objects.create(property=prop, guest=guest, check_in=start + timedelta(days=9),
                                                check_out=start + timedelta(days=10), total_price=Decimal('10'))
        self.delay.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            pms.delete()
            ota.delete()
            local_only.delete()
        self.assertEqual(self._queued(), [(('111',), {})])

    def test_today_filters_use_local_day(self):
        prop = make_property()
        today = timezone.localdate()
        response = self.client.post('/api/reservations/', {
            'property': str(prop.pk), 'guest': str(make_guest().pk), 'adults': 1, 'children': 0,
            'check_in': today.isoformat(), 'check_out': (today + timedelta(days=2)).isoformat(),
            'total_price': '100', 'status': 'confirmed',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.get('/api/reservations/', {'check_in_date': today.isoformat()}).json()['count'], 1)
        self.assertEqual(self.client.get('/api/reservations/',
                                         {'check_out_date': (today + timedelta(days=2)).isoformat()}).json()['count'], 1)
        self.assertEqual(self.client.get('/api/reservations/', {'check_in_date': (today + timedelta(days=1)).isoformat()}).json()['count'], 0)

    def test_bulk_rates_push_once(self):
        prop = make_property()
        self.delay.reset_mock()
        today = timezone.localdate()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/properties/{prop.pk}/rates/bulk/', {
                'date_from': today.isoformat(), 'date_to': (today + timedelta(days=9)).isoformat(),
                'price': '250.00',
            }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyRate.objects.filter(property=prop).count(), 10)
        self.assertEqual(self.delay.call_count, 1)

    def test_broker_failure_does_not_break_save(self):
        self.delay.side_effect = ConnectionError('redis down')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/properties/', {
                'name': 'New', 'phone': '1', 'email': 'a@b.com', 'address': 'x', 'city': 'c', 'country': 'TR',
                'postal_code': '1', 'max_guests': 2, 'bedroom_count': 1, 'bed_count': 1, 'bathroom_count': 1,
                'area': '50', 'base_price': '100',
            }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
