import os
from unittest import mock

import requests
import responses
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from apps.integrations.beds24.client import (
    Beds24Client, Beds24Error, Beds24TransientError, check_post_results, mask_headers,
)
from apps.integrations.models import ChannelConnection, SyncLog
from .helpers import API, FAKE_REFRESH, Beds24TestMixin, fixture


class ClientTests(Beds24TestMixin, TestCase):
    def test_token_is_cached_and_sent_in_token_header(self):
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        client = Beds24Client()
        client.get('/properties')
        client.get('/properties')
        self.assertEqual(len(self.calls_to('/authentication/token')), 1)
        auth_call = self.calls_to('/authentication/token')[0]
        self.assertEqual(auth_call.request.headers['refreshToken'], FAKE_REFRESH)
        call = self.calls_to('/properties')[0]
        self.assertEqual(call.request.headers['token'], 'fake-access-token')
        self.assertNotIn('Authorization', call.request.headers)

    def test_401_refreshes_token_once_and_retries(self):
        self.rsps.add(responses.GET, f'{API}/properties', status=401, json={'success': False, 'error': 'expired'})
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        data = Beds24Client().get('/properties')
        self.assertEqual(data['count'], 1)
        self.assertEqual(len(self.calls_to('/authentication/token')), 2)

    def test_429_and_5xx_are_retried(self):
        self.rsps.add(responses.GET, f'{API}/properties', status=429, json={})
        self.rsps.add(responses.GET, f'{API}/properties', status=503, json={})
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        self.assertEqual(Beds24Client().get('/properties')['count'], 1)
        self.assertEqual(len(self.calls_to('/properties')), 3)

    def test_persistent_5xx_raises_transient_error(self):
        self.rsps.add(responses.GET, f'{API}/properties', status=500, json={'error': 'boom'})
        with self.assertRaises(Beds24TransientError):
            Beds24Client().get('/properties')
        self.assertEqual(len(self.calls_to('/properties')), 4)  # 1 + 3 retry
        self.assertTrue(SyncLog.objects.filter(status='error').exists())

    def test_network_error_raises_transient_error(self):
        self.rsps.add(responses.GET, f'{API}/properties', body=requests.ConnectionError('down'))
        with self.assertRaises(Beds24TransientError):
            Beds24Client().get('/properties')

    def test_4xx_raises_permanent_error(self):
        self.rsps.add(responses.GET, f'{API}/bookings', status=400, json={'success': False, 'error': 'bad'})
        with self.assertRaises(Beds24Error) as ctx:
            Beds24Client().get('/bookings')
        self.assertNotIsInstance(ctx.exception, Beds24TransientError)

    def test_missing_refresh_token_is_explicit(self):
        with mock.patch.dict(os.environ, {'BEDS24_REFRESH_TOKEN': ''}):
            with self.assertRaisesMessage(ImproperlyConfigured, 'BEDS24_REFRESH_TOKEN'):
                Beds24Client().get('/properties')

    def test_sync_log_never_contains_tokens(self):
        self.rsps.add(responses.GET, f'{API}/properties', json=fixture('properties_get.json'))
        Beds24Client().get('/properties')
        self.assertEqual(ChannelConnection.objects.get(provider='beds24').credentials, {})
        for log in SyncLog.objects.all():
            text = f'{log.message} {log.details}'
            self.assertNotIn(FAKE_REFRESH, text)
            self.assertNotIn('fake-access-token', text)
        log = SyncLog.objects.get(action='get /properties')
        self.assertEqual(log.details['status_code'], 200)
        self.assertEqual(log.details['items'], 1)

    def test_get_all_follows_pages(self):
        page1 = fixture('properties_get.json')
        page1['pages'] = {'nextPageExists': True}
        page2 = fixture('properties_get.json')
        page2['data'][0]['id'] = 250002
        self.rsps.add(responses.GET, f'{API}/properties', json=page1)
        self.rsps.add(responses.GET, f'{API}/properties', json=page2)
        items = Beds24Client().get_all('/properties')
        self.assertEqual([i['id'] for i in items], [250001, 250002])

    def test_check_post_results_raises_on_item_errors(self):
        with self.assertRaisesMessage(Beds24Error, 'invalid roomId'):
            check_post_results(fixture('post_error.json'), 'rates.push')

    def test_mask_headers(self):
        self.assertEqual(mask_headers({'token': 'abc', 'refreshToken': 'x', 'accept': 'json'}),
                         {'token': '***', 'refreshToken': '***', 'accept': 'json'})
