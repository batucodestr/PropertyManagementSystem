"""Birleşik mesaj kutusu (Inbox) kuralları.

- Kanal mesajları (Beds24) idempotent içe aktarılır (external_id tekil).
- Cevaplar rezervasyonun kanalından gider: OTA -> kanal yöneticisi (Beds24), direkt -> e-posta.
- Otomatik/zamanlanmış mesaj yoktur; mesajlar Inbox'tan elle gönderilir.
"""
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import Conversation, Message
from .senders import MessageSendError, sender_for, uses_channel_manager

logger = logging.getLogger(__name__)


def channel_of(reservation):
    return reservation.source if uses_channel_manager(reservation) else 'email'


def get_conversation(reservation):
    conversation, _ = Conversation.objects.get_or_create(
        reservation=reservation, defaults={'channel': channel_of(reservation)},
    )
    return conversation


def _touch(conversation, message, unread_increment=0):
    fields = {'last_message_at': message.sent_at, 'last_message_preview': message.body[:200]}
    if conversation.last_message_at and message.sent_at < conversation.last_message_at:
        fields = {}
    if unread_increment:
        fields['unread_count'] = F('unread_count') + unread_increment
    if fields:
        Conversation.objects.filter(pk=conversation.pk).update(**fields)


def record_outgoing(reservation, body, *, source, external_id=None, status=Message.Status.SENT, error='', user=None):
    conversation = get_conversation(reservation)
    message = Message.objects.create(
        conversation=conversation, direction=Message.Direction.OUT, source=source, body=body,
        sent_at=timezone.now(), external_id=external_id or None, status=status, error=error[:1000], sent_by=user,
    )
    _touch(conversation, message)
    return message


def ingest_external(reservation, *, external_id, body, sent_at, source, is_read):
    """Kanal mesajını idempotent içe aktarır. Dönüş: (message, created)."""
    existing = Message.objects.filter(external_id=external_id).first()
    if existing:
        return existing, False
    conversation = get_conversation(reservation)
    incoming = source in (Message.Source.GUEST, Message.Source.SYSTEM)
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=Message.Direction.IN if incoming else Message.Direction.OUT,
                source=source, body=body, sent_at=sent_at or timezone.now(), external_id=external_id,
                status=Message.Status.RECEIVED if incoming else Message.Status.SENT,
                is_read=is_read or not incoming,
            )
    except IntegrityError:
        return Message.objects.get(external_id=external_id), False
    _touch(conversation, message, unread_increment=0 if message.is_read else 1)
    return message, True


def send_reply(conversation, body, user=None):
    reservation = conversation.reservation
    sender = sender_for(reservation)
    try:
        external_id = sender.send(reservation, f'{reservation.property.name}', body)
    except Exception as exc:
        record_outgoing(reservation, body, source=Message.Source.HOST, status=Message.Status.FAILED,
                        error=f'{exc.__class__.__name__}: {exc}', user=user)
        raise MessageSendError(str(exc)) from exc
    return record_outgoing(reservation, body, source=Message.Source.HOST, external_id=external_id, user=user)


def mark_conversation_read(conversation):
    unread = list(conversation.messages.filter(is_read=False))
    if not unread:
        return 0
    ids = [m.external_id for m in unread if m.external_id]
    conversation.messages.filter(is_read=False).update(is_read=True)
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=0)
    if ids and uses_channel_manager(conversation.reservation):
        try:
            sender_for(conversation.reservation).mark_read(ids)
        except Exception as exc:  # okundu bilgisi kanala gidemese de PMS'te okundu
            logger.warning('Okundu bilgisi kanala gönderilemedi: %s', exc.__class__.__name__)
    return len(unread)
