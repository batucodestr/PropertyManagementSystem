from django.conf import settings
from django.core.checks import Warning, register


@register()
def stay_times_check(app_configs, **kwargs):
    """Varsayılan çıkış saati girişten önce olmalı; aksi halde aynı gün değişim (çıkış + yeni giriş)
    çakışma sayılır ve arka arkaya rezervasyonlar reddedilir."""
    try:
        check_in = tuple(int(x) for x in settings.DEFAULT_CHECKIN_TIME.split(':'))
        check_out = tuple(int(x) for x in settings.DEFAULT_CHECKOUT_TIME.split(':'))
    except (AttributeError, ValueError):
        return [Warning('DEFAULT_CHECKIN_TIME / DEFAULT_CHECKOUT_TIME must look like HH:MM.', id='reservations.W001')]
    if check_out >= check_in:
        return [Warning(
            f'DEFAULT_CHECKOUT_TIME ({settings.DEFAULT_CHECKOUT_TIME}) is not earlier than '
            f'DEFAULT_CHECKIN_TIME ({settings.DEFAULT_CHECKIN_TIME}).',
            hint='Örn. DEFAULT_CHECKIN_TIME=15:00, DEFAULT_CHECKOUT_TIME=11:00 (backend/pms/.env). '
                 'Aksi halde aynı gün çıkış + giriş çakışma sayılır.',
            id='reservations.W002',
        )]
    return []
