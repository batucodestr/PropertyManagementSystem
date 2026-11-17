import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import responses
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.testing import AuthenticatedAPITestCase, make_guest, make_property
from apps.integrations.beds24.client import get_connection
from apps.integrations.models import ChannelListing
from apps.integrations.beds24.messaging import poll_messages
from apps.integrations.beds24.tests.helpers import API, Beds24TestMixin
from apps.messaging import services
from apps.messaging.models import Conversation, Message
from apps.reservations.models import Reservation

IST = ZoneInfo('Europe/Istanbul')


def book(prop=None, *, days_ahead=10, nights=3, status='confirmed', **extra):
    start = timezone.localdate(timezone=IST) + timedelta(days=days_ahead)
    return Reservation.objects.create(
        property=prop or make_property(), guest=make_guest(), status=status, total_price=Decimal('100'),
        check_in=datetime.combine(start, time(15), tzinfo=IST),
        check_out=datetime.combine(start + timedelta(days=nights), time(11), tzinfo=IST), **extra,
    )


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


class DirectReplyTests(AuthenticatedAPITestCase):
    def test_reply_to_direct_guest_goes_by_email(self):
        from django.core import mail

        r = book(source='direct')
        conv = services.get_conversation(r)
        response = self.client.post(f'/api/messaging/conversations/{conv.pk}/reply/', {'body': 'Welcome!'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [r.guest.email])
