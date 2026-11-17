"""Beds24 API V2 HTTP istemcisi.

- Kimlik doğrulama: refresh token (.env) -> 24 saatlik token (Django cache'inde).
- Tüm isteklerde header `token: <token>` (Authorization: Bearer DEĞİL).
- 401: token cache'i temizlenir, bir kez yenilenip tekrar denenir.
- 429 / 5xx / bağlantı hatası: exponential backoff ile tekrar.
- Her istek SyncLog'a yazılır; token, header ve istek gövdesi asla loglanmaz.
"""
import logging
import os
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

TOKEN_CACHE_KEY = 'beds24:token'
PROVIDER = 'beds24'
SENSITIVE_HEADERS = {'token', 'refreshtoken', 'authorization', 'cookie'}


class Beds24Error(Exception):
    """Beds24 kalıcı hatası (yanlış istek, yetki vb.)."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class Beds24TransientError(Beds24Error):
    """Tekrar denenebilir hata (429, 5xx, ağ). Celery task'ları bunda retry eder."""


def mask_headers(headers):
    return {k: ('***' if k.lower() in SENSITIVE_HEADERS else v) for k, v in (headers or {}).items()}


def get_refresh_token():
    value = os.getenv('BEDS24_REFRESH_TOKEN')
    if not value:
        raise ImproperlyConfigured('BEDS24_REFRESH_TOKEN .env içinde tanımlı değil')
    return value


def get_connection():
    """Beds24 için tek ChannelConnection kaydı (credentials bilerek boş: gizli bilgi .env'de)."""
    from apps.integrations.models import ChannelConnection

    connection, _ = ChannelConnection.objects.get_or_create(
        provider=PROVIDER, defaults={'name': 'Beds24', 'credentials': {}},
    )
    return connection


def _short_error(response):
    try:
        data = response.json()
    except ValueError:
        return (response.text or '')[:200]
    if isinstance(data, dict):
        return str(data.get('error') or data.get('message') or data)[:200]
    return str(data)[:200]


def _count_items(data):
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get('data'), list):
        return len(data['data'])
    return None


def _cache_call(method, *args):
    """Cache (Redis) erişilemezse işi bozma: token cache'siz kullanılır, sadece loglanır."""
    try:
        return getattr(cache, method)(*args)
    except Exception as exc:
        logger.warning('Token cache erişilemedi (%s): %s', method, exc.__class__.__name__)
        return None


def _error_class(status_code):
    return Beds24TransientError if status_code == 429 or status_code >= 500 else Beds24Error


class Beds24Client:
    def __init__(self, session=None, connection=None):
        self.base = settings.BEDS24_API_BASE
        self.session = session or requests.Session()
        self._connection = connection

    # -- yardımcılar -------------------------------------------------------------
    @property
    def connection(self):
        if self._connection is None:
            self._connection = get_connection()
        return self._connection

    def _log(self, action, status, message, **details):
        from apps.integrations.models import SyncLog

        try:
            SyncLog.objects.create(
                connection=self.connection, action=action[:100], status=status,
                message=message[:500], details=details,
            )
        except Exception:  # Log yazılamaması asıl işi bozmasın.
            logger.exception('SyncLog yazılamadı')

    def _sleep(self, attempt, response=None):
        delay = settings.BEDS24_RETRY_BASE_DELAY * (2 ** attempt)
        retry_after = response.headers.get('Retry-After', '') if response is not None else ''
        if retry_after.isdigit():
            delay = max(delay, min(int(retry_after), 60))
        if delay:
            time.sleep(delay)

    # -- token -------------------------------------------------------------------
    def get_token(self, force_refresh=False):
        if not force_refresh:
            token = _cache_call("get", TOKEN_CACHE_KEY)
            if token:
                return token
        refresh_token = get_refresh_token()
        endpoint = '/authentication/token'
        try:
            response = self.session.get(
                f'{self.base}{endpoint}',
                headers={'refreshToken': refresh_token, 'accept': 'application/json'},
                timeout=settings.BEDS24_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._log('auth.token', 'error', f'Ağ hatası: {exc.__class__.__name__}', endpoint=endpoint)
            raise Beds24TransientError('Beds24 token alınamadı (ağ hatası)') from exc
        if response.status_code != 200:
            message = _short_error(response)
            self._log('auth.token', 'error', message, endpoint=endpoint, status_code=response.status_code)
            raise _error_class(response.status_code)(
                f'Beds24 token alınamadı: {message}', response.status_code,
            )
        data = response.json()
        token = data.get('token')
        if not token:
            raise Beds24Error('Beds24 token cevabında token yok')
        ttl = max(int(data.get('expiresIn') or 86400) - 3600, 60)
        _cache_call("set", TOKEN_CACHE_KEY, token, ttl)
        self._log('auth.token', 'success', 'Token yenilendi', endpoint=endpoint, status_code=200)
        return token

    # -- istek -------------------------------------------------------------------
    def request(self, method, path, *, params=None, json=None, action=None, log=True):
        action = action or f'{method.lower()} {path}'
        url = f'{self.base}{path}'
        refreshed = False
        attempt = 0
        while True:
            token = self.get_token(force_refresh=refreshed)
            started = time.monotonic()
            try:
                response = self.session.request(
                    method, url, params=params, json=json,
                    headers={'token': token, 'accept': 'application/json'},
                    timeout=settings.BEDS24_TIMEOUT,
                )
            except requests.RequestException as exc:
                if attempt < settings.BEDS24_MAX_RETRIES:
                    self._sleep(attempt)
                    attempt += 1
                    continue
                self._log(action, 'error', f'Ağ hatası: {exc.__class__.__name__}', endpoint=path, method=method)
                raise Beds24TransientError(f'Beds24 isteği başarısız: {exc.__class__.__name__}') from exc

            status_code = response.status_code
            details = dict(
                endpoint=path, method=method, status_code=status_code,
                duration_ms=int((time.monotonic() - started) * 1000), attempt=attempt + 1,
                request_cost=response.headers.get('X-RequestCost'),
                credits_remaining=response.headers.get('X-FiveMinCreditLimit-Remaining'),
            )

            if status_code == 401 and not refreshed:
                _cache_call("delete", TOKEN_CACHE_KEY)
                refreshed = True
                continue
            if (status_code == 429 or status_code >= 500) and attempt < settings.BEDS24_MAX_RETRIES:
                self._sleep(attempt, response)
                attempt += 1
                continue
            if status_code >= 400:
                message = _short_error(response)
                self._log(action, 'error', message, **details)
                raise _error_class(status_code)(f'Beds24 {method} {path} -> {status_code}: {message}', status_code)

            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get('success') is False:
                message = str(data.get('error') or 'success=false')[:200]
                self._log(action, 'error', message, **details)
                raise Beds24Error(f'Beds24 {method} {path}: {message}', status_code)

            if log:
                details['items'] = _count_items(data)
                self._log(action, 'success', f'{method} {path} OK', **details)
            return data

    def get(self, path, params=None, **kwargs):
        return self.request('GET', path, params=params, **kwargs)

    def post(self, path, json, **kwargs):
        return self.request('POST', path, json=json, **kwargs)

    def get_all(self, path, params=None, max_pages=50, **kwargs):
        """Sayfalı GET: tüm sayfaların `data` listelerini birleştirir."""
        params = dict(params or {})
        items = []
        page = 1
        while page <= max_pages:
            if page > 1:
                params['page'] = page
            data = self.get(path, params=params, **kwargs) or {}
            items.extend(data.get('data') or [])
            if not (data.get('pages') or {}).get('nextPageExists'):
                break
            page += 1
        return items


def check_post_results(results, action):
    """POST cevabı [{success, new, modified, errors, warnings}] — hata varsa Beds24Error."""
    if not isinstance(results, list):
        results = [results] if results else []
    errors = []
    for item in results:
        if isinstance(item, dict) and item.get('success') is False:
            for err in item.get('errors') or [{'message': 'success=false'}]:
                errors.append(f"{err.get('field', '')}: {err.get('message', '')}".strip(': '))
    if errors:
        raise Beds24Error(f'{action}: ' + '; '.join(errors)[:400])
    return results
