from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Giriş denemelerini IP başına sınırlar (brute-force koruması).

    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] içinde global tanımlıdır ama yalnızca
    login görünümünde (url adı 'token_obtain_pair') çalışır; diğer isteklerde cache anahtarı
    None döner ve sayılmaz. Oran: DEFAULT_THROTTLE_RATES['login'] (LOGIN_THROTTLE_RATE env).
    Sayaç Redis cache'indedir, tüm gunicorn worker'ları arasında paylaşılır.
    """
    scope = 'login'

    def get_cache_key(self, request, view):
        match = getattr(request, 'resolver_match', None)
        if getattr(match, 'url_name', None) != 'token_obtain_pair':
            return None
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}
