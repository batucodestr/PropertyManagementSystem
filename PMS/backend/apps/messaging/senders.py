"""Mesaj gönderim kanalları.

PMS hangi kanalın kullanılacağını sender_for() ile seçer:
- OTA rezervasyonları (Airbnb / Booking.com / diğer, kanal yöneticisi id'si olan): settings.MESSAGE_OTA_SENDER
  (varsayılan Beds24; Beds24'e özel kod apps/integrations/beds24/messaging.py içinde).
- Direkt rezervasyonlar: e-posta (Django e-posta backend'i, SMTP ayarları .env'den).
- WhatsApp: arayüz hazır, henüz implement edilmedi.
"""
from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.utils.module_loading import import_string


class MessageSendError(Exception):
    pass


class MessageSender(ABC):
    channel = ''

    @abstractmethod
    def send(self, reservation, subject, body):
        """Mesajı gönderir; kanal mesaj id'sini (varsa) döndürür. Hata: MessageSendError."""

    def mark_read(self, external_ids):  # opsiyonel
        return None


class EmailSender(MessageSender):
    channel = 'email'

    def send(self, reservation, subject, body):
        if not settings.EMAIL_CONFIGURED:
            raise ImproperlyConfigured('E-posta ayarlı değil: EMAIL_HOST .env içinde tanımlı değil')
        to = (reservation.guest.email or '').strip()
        if not to:
            raise MessageSendError('Guest has no email address')
        EmailMessage(subject=subject or reservation.property.name, body=body, to=[to]).send(fail_silently=False)
        return None


class WhatsAppSender(MessageSender):
    channel = 'whatsapp'

    def send(self, reservation, subject, body):
        raise NotImplementedError('WhatsApp gönderimi henüz implement edilmedi')


def ota_sender():
    return import_string(settings.MESSAGE_OTA_SENDER)()


def uses_channel_manager(reservation):
    return bool(reservation.external_source_id) and reservation.source != 'direct'


def sender_for(reservation):
    return ota_sender() if uses_channel_manager(reservation) else EmailSender()
