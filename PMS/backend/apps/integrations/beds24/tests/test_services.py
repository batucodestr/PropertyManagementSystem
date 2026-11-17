from datetime import timedelta
from decimal import Decimal
from unittest import mock

import responses
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.testing import make_guest, make_property
from apps.integrations.beds24 import services
from apps.integrations.beds24.client import Beds24Error, get_connection
from apps.integrations.models import ChannelListing, SyncLog, WebhookEvent
from apps.properties.models import DailyRate
from apps.reservations.models import AvailabilityBlock, Reservation, ReservationStatusHistory
from .helpers import API, FAKE_SECRET, Beds24TestMixin, booking, bookings_response, fixture


def make_listing(prop, listing_id='250001', room_id='560001', **extra):
    return ChannelListing.objects.create(
        connection=get_connection(), property=prop,
        external_listing_id=listing_id, external_room_id=room_id, **extra,
    )


class SyncPropertyTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        self.rsps.add(responses.POST, f'{API}/inventory/rooms/calendar', json=fixture('calendar_post.json'))

    def test_creates_property_and_room_and_stores_ids(self):
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('properties_post_new.json'))
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        listing = services.sync_property(self.prop)
        self.assertEqual((listing.external_listing_id, listing.external_room_id), ('250001', '560001'))
        self.assertEqual(listing.sync_status, ChannelListing.SyncStatus.OK)
        self.assertIsNotNone(listing.last_synced_at)
        payload = self.body(self.calls_to('/properties', 'POST')[0])[0]
        self.assertNotIn('id', payload)
        self.assertEqual(payload['roomTypes'][0]['qty'], 1)
        self.assertEqual(payload['roomTypes'][0]['rackRate'], 100.0)
        self.assertEqual(payload['roomTypes'][0]['maxPeople'], 4)
        self.assertEqual(len(self.calls_to('/inventory/rooms/calendar')), 1)

    def test_updates_existing_mapping_with_ids(self):
        make_listing(self.prop)
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('properties_post_modified.json'))
        services.sync_property(self.prop)
        payload = self.body(self.calls_to('/properties', 'POST')[0])[0]
        self.assertEqual(payload['id'], 250001)
        self.assertEqual(payload['roomTypes'][0]['id'], 560001)
        self.assertEqual(ChannelListing.objects.count(), 1)

    def test_error_is_recorded_on_listing(self):
        make_listing(self.prop)
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('post_error.json'))
        with self.assertRaises(Beds24Error):
            services.sync_property(self.prop)
        listing = ChannelListing.objects.get()
        self.assertEqual(listing.sync_status, ChannelListing.SyncStatus.ERROR)
        self.assertIn('invalid roomId', listing.last_error)

    @override_settings(PUBLIC_BASE_URL='https://pms.example.com')
    def test_webhook_url_is_registered_when_public_url_set(self):
        make_listing(self.prop)
        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('properties_post_modified.json'))
        services.sync_property(self.prop)
        payload = self.body(self.calls_to('/properties', 'POST')[0])[0]
        self.assertEqual(payload['webhooks']['url'],
                         f'https://pms.example.com/api/integrations/beds24/webhook/{FAKE_SECRET}/')
        # Webhook URL'si (secret içerir) loglara yazılmaz.
        for log in SyncLog.objects.all():
            self.assertNotIn(FAKE_SECRET, f'{log.message} {log.details}')

    def test_link_property(self):
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        listing = services.link_property(self.prop, 250001)
        self.assertEqual(listing.external_room_id, '560001')


class PushRatesTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property(base_price=Decimal('100.00'))
        self.listing = make_listing(self.prop, airbnb_markup_percent=Decimal('18.34'))
        self.rsps.add(responses.POST, f'{API}/inventory/rooms/calendar', json=fixture('calendar_post.json'))
        self.today = timezone.localdate()

    def test_sends_merged_ranges_in_single_request(self):
        DailyRate.objects.create(property=self.prop, date=self.today + timedelta(days=3), price=Decimal('200'))
        AvailabilityBlock.objects.create(property=self.prop, start_date=self.today + timedelta(days=5),
                                         end_date=self.today + timedelta(days=6))
        services.push_rates(self.prop, self.today, self.today + timedelta(days=9))
        calls = self.calls_to('/inventory/rooms/calendar')
        self.assertEqual(len(calls), 1)
        body = self.body(calls[0])
        self.assertEqual(body[0]['roomId'], 560001)
        cal = body[0]['calendar']
        self.assertEqual(len(cal), 5)  # base | daily | base | blackout | base
        self.assertEqual(cal[1]['price1'], 200.0)
        self.assertEqual(cal[1]['price2'], 236.68)
        self.assertEqual(cal[3]['override'], 'blackout')

    def test_window_is_clamped_to_today_and_365_days(self):
        services.push_rates(self.prop, self.today - timedelta(days=10), self.today + timedelta(days=1000))
        cal = self.body(self.calls_to('/inventory/rooms/calendar')[0])[0]['calendar']
        self.assertEqual(cal[0]['from'], self.today.isoformat())
        self.assertEqual(cal[-1]['to'], (self.today + timedelta(days=364)).isoformat())

    def test_unlinked_property_is_noop(self):
        other = make_property(name='Other')
        self.assertEqual(services.push_rates(other), 0)
        self.assertEqual(len(self.calls_to('/inventory/rooms/calendar')), 0)

    def test_inactive_property_is_blacked_out(self):
        self.prop.is_active = False
        self.prop.save()
        services.push_rates(self.prop, self.today, self.today + timedelta(days=2))
        cal = self.body(self.calls_to('/inventory/rooms/calendar')[0])[0]['calendar']
        self.assertEqual(len(cal), 1)
        self.assertEqual(cal[0]['override'], 'blackout')


class UpsertBookingTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        make_listing(self.prop)

    def test_creates_reservation_guest_and_history(self):
        reservation, result = services.upsert_booking(booking())
        self.assertEqual(result, 'created')
        self.assertEqual(reservation.source, 'airbnb')
        self.assertEqual(reservation.status, 'confirmed')
        self.assertEqual(reservation.total_price, Decimal('4800.50'))
        self.assertEqual(reservation.channel_booking_ref, 'HMABC12345')
        self.assertEqual(reservation.guest.email, 'jane.doe.abc123@guest.airbnb.com')
        self.assertEqual(ReservationStatusHistory.objects.filter(reservation=reservation).count(), 1)

    def test_is_idempotent(self):
        services.upsert_booking(booking())
        reservation, result = services.upsert_booking(booking())
        self.assertEqual(result, 'unchanged')
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(ReservationStatusHistory.objects.count(), 1)

    def test_modification_and_cancellation(self):
        services.upsert_booking(booking())
        reservation, result = services.upsert_booking(booking(departure='2030-07-06', price=6000))
        self.assertEqual(result, 'updated')
        self.assertEqual(reservation.total_price, Decimal('6000.00'))
        reservation, result = services.upsert_booking(booking(status='cancelled'))
        self.assertEqual(reservation.status, 'cancelled')
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(
            list(ReservationStatusHistory.objects.order_by('created_at').values_list('old_status', 'new_status')),
            [('', 'confirmed'), ('confirmed', 'cancelled')],
        )

    def test_existing_guest_is_reused_by_email(self):
        guest = make_guest(email='JANE.doe.abc123@guest.airbnb.com')
        reservation, _ = services.upsert_booking(booking())
        self.assertEqual(reservation.guest, guest)

    def test_unknown_cancelled_and_inquiry_are_skipped(self):
        self.assertEqual(services.upsert_booking(booking(status='cancelled'))[1], 'skipped:cancelled')
        self.assertEqual(services.upsert_booking(booking(status='inquiry'))[1], 'skipped:inquiry')
        self.assertEqual(Reservation.objects.count(), 0)

    def test_unlinked_property_is_skipped(self):
        self.assertEqual(services.upsert_booking(booking(propertyId=999))[1], 'skipped:unlinked_property')

    def test_completed_reservation_is_not_reopened(self):
        reservation, _ = services.upsert_booking(booking())
        Reservation.objects.filter(pk=reservation.pk).update(status='completed')
        reservation, _ = services.upsert_booking(booking(status='confirmed'))
        self.assertEqual(reservation.status, 'completed')

    def test_overlap_is_saved_but_logged(self):
        services.upsert_booking(booking())
        services.upsert_booking(booking(id=77700002, apiReference='HMXYZ'))
        self.assertEqual(Reservation.objects.count(), 2)
        self.assertTrue(SyncLog.objects.filter(action='booking.overlap').exists())

    def test_echo_of_pms_reservation_links_instead_of_duplicating(self):
        local = Reservation.objects.create(
            property=self.prop, guest=make_guest(), check_in=timezone.now() + timedelta(days=30),
            check_out=timezone.now() + timedelta(days=32), total_price=Decimal('300'), status='confirmed',
        )
        reservation, _ = services.upsert_booking(booking(channel=None, apiSource='', apiReference=str(local.pk)))
        self.assertEqual(reservation.pk, local.pk)
        self.assertEqual(Reservation.objects.count(), 1)
        local.refresh_from_db()
        self.assertEqual(local.external_source_id, '77700001')
        self.assertEqual(local.total_price, Decimal('300.00'))  # PMS verisi korunur
        self.assertEqual(local.source, 'direct')


class PullAndWebhookTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        make_listing(self.prop)

    def test_pull_bookings_uses_modified_from_and_moves_cursor(self):
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(booking()))
        summary = services.pull_bookings()
        self.assertEqual(summary, {'created': 1})
        request = self.calls_to('/bookings')[0].request
        self.assertIn('modifiedFrom=', request.url)
        self.assertIn('status=cancelled', request.url)
        self.assertIn('propertyId=250001', request.url)
        first_cursor = get_connection().last_synced_at
        self.assertIsNotNone(first_cursor)
        services.pull_bookings()
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertGreater(get_connection().last_synced_at, first_cursor)

    def test_pull_bookings_continues_after_bad_record(self):
        bad = booking(id=77700009, arrival='not-a-date')
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(bad, booking()))
        summary = services.pull_bookings()
        self.assertEqual(summary, {'error': 1, 'created': 1})

    def test_webhook_wrong_secret_is_404(self):
        client = APIClient()
        url = reverse('beds24-webhook', kwargs={'secret': 'wrong'})
        self.assertEqual(client.post(url, {'booking': {'id': 1}}, format='json').status_code, 404)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_webhook_without_configured_secret_is_404(self):
        with mock.patch.dict('os.environ', {'BEDS24_WEBHOOK_SECRET': ''}):
            url = reverse('beds24-webhook', kwargs={'secret': FAKE_SECRET})
            self.assertEqual(APIClient().post(url, {}, format='json').status_code, 404)

    def test_webhook_saves_sanitized_event_and_imports_authoritative_booking(self):
        # Webhook gövdesindeki fiyat yanlış olsa bile GET /bookings'teki otoriter veri kullanılır.
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(booking()))
        url = reverse('beds24-webhook', kwargs={'secret': FAKE_SECRET})
        payload = {'timeStamp': '2030-06-01T10:00:00Z',
                   'booking': {'id': 77700001, 'propertyId': 250001, 'price': 1, 'firstName': 'Jane',
                               'email': 'x@example.com'}}
        response = APIClient().post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        event = WebhookEvent.objects.get()
        self.assertNotIn('email', event.payload['booking'])
        self.assertNotIn('firstName', event.payload['booking'])
        self.assertTrue(event.processed)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.total_price, Decimal('4800.50'))
        self.assertIn('id=77700001', self.calls_to('/bookings')[0].request.url)

    def test_duplicate_webhooks_create_single_reservation(self):
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(booking()))
        url = reverse('beds24-webhook', kwargs={'secret': FAKE_SECRET})
        for _ in range(2):
            APIClient().post(url, {'booking': {'id': 77700001}}, format='json')
        self.assertEqual(WebhookEvent.objects.count(), 2)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_webhook_cancellation(self):
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(booking()))
        self.rsps.add(responses.GET, f'{API}/bookings', json=bookings_response(booking(status='cancelled')))
        url = reverse('beds24-webhook', kwargs={'secret': FAKE_SECRET})
        APIClient().post(url, {'booking': {'id': 77700001}}, format='json')
        APIClient().post(url, {'booking': {'id': 77700001}}, format='json')
        self.assertEqual(Reservation.objects.get().status, 'cancelled')


class PushBookingTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        make_listing(self.prop)
        self.reservation = Reservation.objects.create(
            property=self.prop, guest=make_guest(), check_in=timezone.now() + timedelta(days=30),
            check_out=timezone.now() + timedelta(days=33), total_price=Decimal('450'), status='confirmed',
        )

    def test_creates_booking_and_stores_external_id(self):
        self.rsps.add(responses.POST, f'{API}/bookings', json=fixture('bookings_post_new.json'))
        services.push_booking(self.reservation)
        payload = self.body(self.calls_to('/bookings', 'POST')[0])[0]
        self.assertEqual(payload['roomId'], 560001)
        self.assertEqual(payload['status'], 'confirmed')
        self.assertEqual(payload['apiReference'], str(self.reservation.pk))
        self.assertNotIn('id', payload)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.external_source_id, '88800001')

    def test_updates_existing_booking(self):
        Reservation.objects.filter(pk=self.reservation.pk).update(external_source_id='88800001')
        self.reservation.refresh_from_db()
        self.reservation.status = 'cancelled'
        self.rsps.add(responses.POST, f'{API}/bookings', json=[{'success': True, 'modified': {'id': 88800001}}])
        services.push_booking(self.reservation)
        payload = self.body(self.calls_to('/bookings', 'POST')[0])[0]
        self.assertEqual((payload['id'], payload['status']), (88800001, 'cancelled'))

    def test_never_pushed_cancelled_is_skipped(self):
        self.reservation.status = 'cancelled'
        self.assertIsNone(services.push_booking(self.reservation))
        self.assertEqual(len(self.calls_to('/bookings', 'POST')), 0)


class LinkWithoutRoomTests(Beds24TestMixin, TestCase):
    def test_link_property_without_room_then_sync_creates_room(self):
        prop = make_property()
        empty = fixture('properties_get.json')
        empty['data'][0]['roomTypes'] = []
        self.rsps.add(responses.GET, f'{API}/properties', json=empty)
        listing = services.link_property(prop, 250001)
        self.assertEqual((listing.external_listing_id, listing.external_room_id), ('250001', ''))

        self.rsps.add(responses.POST, f'{API}/properties', json=fixture('properties_post_modified.json'))
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        self.rsps.add(responses.POST, f'{API}/inventory/rooms/calendar', json=fixture('calendar_post.json'))
        listing = services.sync_property(prop)
        payload = self.body(self.calls_to('/properties', 'POST')[0])[0]
        self.assertEqual(payload['id'], 250001)
        self.assertNotIn('id', payload['roomTypes'][0])  # yeni oda oluşturulur
        self.assertEqual(listing.external_room_id, '560001')

    def test_link_unknown_property_fails(self):
        self.rsps.add(responses.GET, f'{API}/properties', json={'success': True, 'data': [], 'pages': {}})
        with self.assertRaisesMessage(Beds24Error, 'bulunamadı'):
            services.link_property(make_property(), 999)


@override_settings(CHANNEL_COMMISSIONS={'airbnb': '15.5', 'booking': '15', 'direct': '0', 'other': '0'})
class BookingFinanceTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        make_listing(make_property())

    def test_channel_commission_tax_and_cleaning_fee(self):
        items = [
            {'type': 'charge', 'description': 'Accommodation', 'qty': 1, 'amount': 4300.5, 'lineTotal': 4300.5},
            {'type': 'charge', 'description': 'Cleaning fee', 'qty': 1, 'amount': 500, 'lineTotal': 500},
            {'type': 'payment', 'description': 'Cleaning paid', 'qty': 1, 'amount': 500},
        ]
        reservation, _ = services.upsert_booking(booking(commission=744.08, tax=100, invoiceItems=items))
        self.assertEqual(reservation.channel_commission, Decimal('744.08'))
        self.assertFalse(reservation.commission_is_estimated)
        self.assertEqual(reservation.cleaning_fee, Decimal('500.00'))
        self.assertEqual(reservation.net_amount, Decimal('3956.42'))  # 4800.50 - 744.08 - 100
        self.assertEqual(reservation.financial_transactions.get(category='reservation').amount,
                         Decimal('3956.42'))

    def test_missing_commission_is_estimated_and_stable(self):
        reservation, _ = services.upsert_booking(booking(commission=0))
        self.assertTrue(reservation.commission_is_estimated)
        self.assertEqual(reservation.channel_commission, Decimal('744.08'))  # 4800.50 * 15.5%
        _, result = services.upsert_booking(booking(commission=0))
        self.assertEqual(result, 'unchanged')

    def test_cancellation_removes_income(self):
        reservation, _ = services.upsert_booking(booking())
        services.upsert_booking(booking(status='cancelled'))
        self.assertFalse(reservation.financial_transactions.filter(category='reservation').exists())



class ManualChannelReservationTests(Beds24TestMixin, TestCase):
    """PMS'e elle girilen Airbnb rezervasyonu: Beds24'e gider, geri geldiğinde PMS verisi korunur."""

    def test_push_and_echo_keep_pms_source(self):
        prop = make_property()
        make_listing(prop)
        r = Reservation.objects.create(
            property=prop, guest=make_guest(), check_in=timezone.now() + timedelta(days=30),
            check_out=timezone.now() + timedelta(days=32), total_price=Decimal('300'), status='confirmed',
            source='airbnb',
        )
        self.rsps.add(responses.POST, f'{API}/bookings', json=fixture('bookings_post_new.json'))
        services.push_booking(r)
        payload = self.body(self.calls_to('/bookings', 'POST')[0])[0]
        self.assertEqual(payload['referer'], 'PMS (Airbnb)')
        r.refresh_from_db()
        self.assertEqual(r.external_source_id, '88800001')
        # Beds24'ten "direkt" (kanalsız) olarak geri gelir -> kaynak Airbnb kalmalı.
        services.upsert_booking(booking(id=88800001, channel=None, apiSource='', apiReference=str(r.pk), commission=0))
        r.refresh_from_db()
        self.assertEqual((r.source, r.created_via_channel), ('airbnb', False))
        self.assertEqual(Reservation.objects.count(), 1)

    def test_imported_booking_is_marked_as_channel(self):
        make_listing(make_property())
        reservation, _ = services.upsert_booking(booking())
        self.assertTrue(reservation.created_via_channel)
