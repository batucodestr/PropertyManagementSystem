"""Beds24 testleri için ortak yardımcılar. Gerçek API'ye asla istek gitmez (responses ile mock)."""
import copy
import json
import os
from pathlib import Path
from unittest import mock

import responses
from django.conf import settings
from django.core.cache import cache

FIXTURES = Path(__file__).parent / 'fixtures'
API = settings.BEDS24_API_BASE
FAKE_REFRESH = 'test-refresh-token-value'
FAKE_SECRET = 'test-webhook-secret-value'


def fixture(name):
    return copy.deepcopy(json.loads((FIXTURES / name).read_text(encoding='utf-8')))


def booking(**overrides):
    data = fixture('booking_airbnb.json')
    item = data['data'][0]
    item.update(overrides)
    return item


def bookings_response(*items):
    return {'success': True, 'type': 'booking', 'count': len(items),
            'pages': {'nextPageExists': False}, 'data': list(items)}


class Beds24TestMixin:
    """Ortam değişkenlerini sahte değerlerle doldurur, token cache'ini temizler, HTTP'yi mock'lar."""

    def setUp(self):
        super().setUp()
        cache.clear()
        env = mock.patch.dict(os.environ, {
            'BEDS24_REFRESH_TOKEN': FAKE_REFRESH,
            'BEDS24_WEBHOOK_SECRET': FAKE_SECRET,
        })
        env.start()
        self.addCleanup(env.stop)
        self.rsps = responses.RequestsMock(assert_all_requests_are_fired=False)
        self.rsps.start()
        self.addCleanup(self.rsps.stop)
        self.addCleanup(self.rsps.reset)
        self.rsps.add(responses.GET, f'{API}/authentication/token', json=fixture('token.json'))

    def calls_to(self, path, method=None):
        return [
            c for c in self.rsps.calls
            if c.request.url.split('?')[0] == f'{API}{path}' and (method is None or c.request.method == method)
        ]

    def body(self, call):
        return json.loads(call.request.body)
