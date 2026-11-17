import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import responses
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.integrations.beds24.client import get_connection
from apps.integrations.beds24.messaging import poll_messages
from apps.integrations.beds24.tests.helpers import API, Beds24TestMixin
from apps.integrations.models import ChannelListing, SyncLog
from apps.messaging import services
from apps.messaging.models import Conversation, Message, MessageTemplate, ScheduledMessage
from apps.properties.models import PropertyAccessInfo
from apps.reservations.models import Reservation

IST = ZoneInfo('Europe/Istanbul')
T = MessageTemplate.Trigger


def template(trigger, body='Hi {guest_first_name}', **extra):
    return MessageTemplate.objects.create(name=trigger, trigger=trigger, body=body, **extra)


def book(prop=None, *, days_ahead=10, nights=3, status='confirmed', **extra):
    start = timezone.localdate(timezone=IST) + timedelta(days=days_ahead)
    return Reservation.objects.create(
        property=prop or make_property(), guest=make_guest(), status=status, total_price=Decimal('100'),
        check_in=datetime.combine(start, time(15), tzinfo=IST),
        check_out=datetime.combine(start + timedelta(days=nights), time(11), tzinfo=IST), **extra,
    )


def scheduled(reservation, trigger):
    return ScheduledMessage.objects.get(reservation=reservation, template__trigger=trigger)


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul', MESSAGE_DEFAULT_LANGUAGE='en')
class SchedulingTests(TestCase):
    def setUp(self):
        template(T.BOOKING_CONFIRMED)
        template(T.BEFORE_CHECK_IN, offset_hours=24)
        template(T.CHECK_IN_DAY, send_time=time(9, 30))
        template(T.CHECK_OUT_MORNING)
        template(T.AFTER_CHECK_OUT, offset_hours=6)

    def test_confirmed_reservation_schedules_each_trigger_once(self):
        r = book()
        self.assertEqual(ScheduledMessage.objects.filter(reservation=r).count(), 5)
        self.assertEqual(scheduled(r, T.BEFORE_CHECK_IN).send_at, r.check_in - timedelta(hours=24))
        self.assertEqual(scheduled(r, T.CHECK_IN_DAY).send_at.astimezone(IST).time(), time(9, 30))
        self.assertEqual(scheduled(r, T.CHECK_OUT_MORNING).send_at.astimezone(IST).time(), time(8, 0))
        self.assertEqual(scheduled(r, T.AFTER_CHECK_OUT).send_at, r.check_out + timedelta(hours=6))
        r.save()
        self.assertEqual(ScheduledMessage.objects.filter(reservation=r).count(), 5)

    def test_pending_reservation_schedules_nothing(self):
        self.assertFalse(ScheduledMessage.objects.filter(reservation=book(status='pending')).exists())

    def test_date_change_reschedules_and_cancel_revive(self):
        r = book()
        confirmed_at = scheduled(r, T.BOOKING_CONFIRMED).send_at
        r.check_in += timedelta(days=2)
        r.check_out += timedelta(days=2)
        r.save()
        self.assertEqual(scheduled(r, T.BEFORE_CHECK_IN).send_at, r.check_in - timedelta(hours=24))
        self.assertEqual(scheduled(r, T.BOOKING_CONFIRMED).send_at, confirmed_at)  # sabit kalır
        r.status = 'cancelled'
        r.save()
        self.assertEqual(set(ScheduledMessage.objects.filter(reservation=r).values_list('status', flat=True)),
                         {'cancelled'})
        r.status = 'confirmed'
        r.save()
        self.assertEqual(scheduled(r, T.CHECK_IN_DAY).status, 'pending')

    def test_last_minute_booking_sends_check_in_info_now(self):
        now = timezone.now()
        r = book(days_ahead=0, nights=2)  # bugün 15:00 giriş
        msg = scheduled(r, T.BEFORE_CHECK_IN)
        if r.check_in > now:
            self.assertEqual(msg.status, 'pending')
            self.assertLessEqual(msg.send_at, timezone.now())

    def test_too_late_messages_are_skipped(self):
        r = book(days_ahead=-10, nights=3)  # konaklama bitti
        self.assertEqual(scheduled(r, T.AFTER_CHECK_OUT).status, 'skipped')
        self.assertEqual(scheduled(r, T.CHECK_IN_DAY).status, 'skipped')

    def test_language_selection(self):
        tr = template(T.BEFORE_CHECK_IN, body='Merhaba', language='tr', offset_hours=24)
        r = book(guest_language='tr')
        self.assertEqual(scheduled(r, T.BEFORE_CHECK_IN).template, tr)
        other = book(guest_language='de')
        self.assertEqual(scheduled(other, T.BEFORE_CHECK_IN).template.language, 'en')


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul')
class SendingTests(Beds24TestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property(name='Sea View', address='1 Beach Rd')
        PropertyAccessInfo.objects.create(property=self.prop, wifi_name='SeaNet', wifi_password='p4ss', door_code='4321')
        self.tpl = template(T.BOOKING_CONFIRMED, subject='Welcome to {property_name}',
                            body='Hi {guest_first_name}, door {door_code}, wifi {wifi_name}/{wifi_password} {unknown}')

    def test_direct_reservation_gets_email_exactly_once(self):
        r = book(self.prop, source='direct')
        self.assertEqual(services.send_due_messages(), {'sent': 1})
        self.assertEqual(services.send_due_messages(), {})
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, 'Welcome to Sea View')
        self.assertIn('door 4321, wifi SeaNet/p4ss {unknown}', email.body)
        sm = scheduled(r, T.BOOKING_CONFIRMED)
        self.assertEqual((sm.status, sm.channel), ('sent', 'email'))
        msg = Message.objects.get()
        self.assertEqual((msg.direction, msg.source), ('out', 'auto'))

    def test_guest_without_email_fails_without_retry(self):
        r = book(self.prop, source='direct')
        r.guest.email = ''
        r.guest.save()
        self.assertEqual(services.send_due_messages(), {'failed': 1})
        self.assertIn('no email', scheduled(r, T.BOOKING_CONFIRMED).error)

    def test_ota_reservation_goes_through_beds24(self):
        r = book(self.prop, source='airbnb', external_source_id='777')
        self.rsps.add(responses.POST, f'{API}/bookings/messages', json=[{'success': True, 'new': {'id': 9001}}])
        self.assertEqual(services.send_due_messages(), {'sent': 1})
        body = json.loads(self.calls_to('/bookings/messages', 'POST')[0].request.body)[0]
        self.assertEqual((body['bookingId'], body['source']), (777, 'host'))
        self.assertIn('4321', body['message'])
        self.assertEqual(Message.objects.get().external_id, 'beds24:9001')
        self.assertEqual(len(mail.outbox), 0)
        # mesaj gövdesi (kapı kodu) loglara yazılmaz
        for log in SyncLog.objects.all():
            self.assertNotIn('4321', f'{log.message} {log.details}')

    def test_transient_error_is_retried_later(self):
        book(self.prop, source='airbnb', external_source_id='777')
        self.rsps.add(responses.POST, f'{API}/bookings/messages', status=503, json={})
        self.assertEqual(services.send_due_messages(), {'retry': 1})
        sm = ScheduledMessage.objects.get()
        self.assertEqual((sm.status, sm.attempts), ('pending', 1))
        self.assertGreater(sm.send_at, timezone.now())

    def test_cancelled_reservation_does_not_send(self):
        r = book(self.prop, source='direct')
        Reservation.objects.filter(pk=r.pk).update(status='cancelled')  # sinyal atlanmış olsa bile
        self.assertEqual(services.send_due_messages(), {'cancelled': 1})
        self.assertEqual(len(mail.outbox), 0)


@override_settings(PROPERTY_TIMEZONE='Europe/Istanbul')
class InboxTests(Beds24TestMixin, AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.prop = make_property()
        ChannelListing.objects.create(connection=get_connection(), property=self.prop,
                                      external_listing_id='250001', external_room_id='560001')
        self.r = book(self.prop, source='airbnb', external_source_id='777')

    def poll_payload(self, *items):
        return {'success': True, 'pages': {'nextPageExists': False}, 'data': list(items)}

    def test_poll_is_idempotent_and_counts_unread(self):
        items = [
            {'id': 1, 'bookingId': 777, 'source': 'guest', 'message': 'Hello!', 'read': False,
             'time': '2030-06-01T10:00:00Z'},
            {'id': 2, 'bookingId': 777, 'source': 'host', 'message': 'Hi', 'read': True, 'time': '2030-06-01T10:05:00Z'},
            {'id': 3, 'bookingId': 999, 'source': 'guest', 'message': 'unknown booking'},
            {'id': 4, 'bookingId': 777, 'source': 'internalNote', 'message': 'note'},
        ]
        self.rsps.add(responses.GET, f'{API}/bookings/messages', json=self.poll_payload(*items))
        self.assertEqual(poll_messages(), {'new': 2, 'skipped': 2})
        self.assertEqual(poll_messages(), {'known': 2, 'skipped': 2})
        conv = Conversation.objects.get()
        self.assertEqual((conv.unread_count, conv.channel, conv.last_message_preview), (1, 'airbnb', 'Hi'))
        self.assertIn('maxAge=2', self.calls_to('/bookings/messages')[0].request.url)

    def test_inbox_api_reply_and_read(self):
        self.rsps.add(responses.GET, f'{API}/bookings/messages', json=self.poll_payload(
            {'id': 1, 'bookingId': 777, 'source': 'guest', 'message': 'Where is the key?', 'read': False}))
        poll_messages()
        conv = self.client.get('/api/messaging/conversations/').json()['results'][0]
        self.assertEqual(conv['unread_count'], 1)
        self.rsps.add(responses.POST, f'{API}/bookings/messages', json=[{'success': True, 'new': {'id': 55}}])
        response = self.client.post(f"/api/messaging/conversations/{conv['id']}/reply/", {'body': 'In the lockbox'},
                                    format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.rsps.add(responses.PATCH, f'{API}/bookings/messages', json={'success': True})
        self.assertEqual(self.client.post(f"/api/messaging/conversations/{conv['id']}/read/").json(), {'marked': 1})
        self.assertIn('messageId=1', self.calls_to('/bookings/messages', 'PATCH')[0].request.url)
        thread = self.client.get(f"/api/messaging/conversations/{conv['id']}/messages/").json()
        self.assertEqual([m['direction'] for m in thread], ['in', 'out'])
        # cevap polling'de geri gelince çift kayıt olmaz
        self.rsps.replace(responses.GET, f'{API}/bookings/messages', json=self.poll_payload(
            {'id': 55, 'bookingId': 777, 'source': 'host', 'message': 'In the lockbox', 'read': True}))
        poll_messages()
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(self.client.get('/api/messaging/conversations/unread-count/').json(), {'unread': 0})

    def test_reply_failure_returns_502_and_is_recorded(self):
        conv = services.get_conversation(self.r)
        self.rsps.add(responses.POST, f'{API}/bookings/messages',
                      json=[{'success': False, 'errors': [{'field': 'bookingId', 'message': 'bad'}]}])
        response = self.client.post(f'/api/messaging/conversations/{conv.pk}/reply/', {'body': 'x'}, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(Message.objects.get().status, 'failed')

    def test_template_crud_preview_and_scheduled_list(self):
        response = self.client.post('/api/messaging/templates/', {
            'name': 'Welcome', 'trigger': 'booking_confirmed', 'body': 'Hi {guest_first_name} at {property_name}',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        tpl_id = response.json()['id']
        preview = self.client.post(f'/api/messaging/templates/{tpl_id}/preview/', {'reservation': str(self.r.pk)},
                                   format='json').json()
        self.assertEqual(preview['body'], f'Hi {self.r.guest.first_name} at {self.prop.name}')
        self.r.save()  # yeni şablon için planla
        listed = self.client.get('/api/messaging/scheduled/', {'reservation': str(self.r.pk)}).json()
        self.assertEqual(listed['count'], 1)
        sm_id = listed['results'][0]['id']
        self.assertEqual(self.client.post(f'/api/messaging/scheduled/{sm_id}/cancel/').json()['status'], 'cancelled')
        self.assertEqual(self.client.post(f'/api/messaging/scheduled/{sm_id}/cancel/').status_code, 409)


class AccessInfoSecurityTests(AuthenticatedAPITestCase):
    def test_wifi_and_door_code_never_in_public_api(self):
        prop = make_property()
        PropertyAccessInfo.objects.create(property=prop, wifi_name='SecretNet', wifi_password='wifi-secret-pass',
                                          door_code='998877', check_in_instructions='key under mat')
        self.client.force_authenticate(None)
        for url in ('/api/public/properties/', f'/api/public/properties/{prop.pk}/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            text = response.content.decode()
            for secret in ('SecretNet', 'wifi-secret-pass', '998877', 'key under mat', 'wifi', 'door_code'):
                self.assertNotIn(secret, text, url)
        self.assertEqual(self.client.get(f'/api/properties/{prop.pk}/access-info/').status_code, 401)

    def test_staff_can_edit_access_info(self):
        prop = make_property()
        response = self.client.put(f'/api/properties/{prop.pk}/access-info/', {
            'wifi_name': 'Net', 'wifi_password': 'x', 'door_code': '1234',
            'check_in_instructions': '', 'house_rules': '',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f'/api/properties/{prop.pk}/access-info/').json()['door_code'], '1234')
