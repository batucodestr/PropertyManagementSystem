"""Otomatik mesaj zamanlama/gönderim ve birleşik mesaj kutusu kuralları.

Zamanlama (yerel saat = PROPERTY_TIMEZONE):
    booking_confirmed : onay anı + offset_hours
    before_check_in   : check-in - offset_hours
    check_in_day      : check-in günü, send_time (varsayılan 10:00)
    check_out_morning : check-out günü, send_time (varsayılan 08:00)
    after_check_out   : check-out + offset_hours
Hesaplanan zaman geçmişte kaldıysa: mesaj hâlâ anlamlıysa (ör. son dakika rezervasyonda giriş
bilgileri) hemen gönderilir, değilse 'skipped' olur.
Rezervasyon iptal / no-show / pending'e dönerse bekleyen mesajlar iptal edilir.
Gönderim: pending -> sending (satır kilidiyle) -> sent | failed. 'sending'de kalan mesaj tekrar
gönderilmez: aynı mesaj asla iki kez gitmez.
"""
import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.properties.models import PropertyAccessInfo
from apps.properties.pricing import property_tz

from .models import Conversation, Message, MessageTemplate, ScheduledMessage
from .senders import MessageSendError, sender_for, uses_channel_manager

logger = logging.getLogger(__name__)
Trigger = MessageTemplate.Trigger
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=10)
DEFAULT_SEND_TIMES = {Trigger.CHECK_IN_DAY: time(10, 0), Trigger.CHECK_OUT_MORNING: time(8, 0)}


# --------------------------------------------------------------------------- render
class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def template_context(reservation):
    tz = property_tz()
    ci, co = reservation.check_in.astimezone(tz), reservation.check_out.astimezone(tz)
    prop, guest = reservation.property, reservation.guest
    access = PropertyAccessInfo.objects.filter(property=prop).first()
    return {
        'guest_first_name': guest.first_name,
        'guest_last_name': guest.last_name,
        'property_name': prop.name,
        'check_in_date': ci.strftime('%d.%m.%Y'),
        'check_in_time': ci.strftime('%H:%M'),
        'check_out_date': co.strftime('%d.%m.%Y'),
        'check_out_time': co.strftime('%H:%M'),
        'nights': max((co.date() - ci.date()).days, 1),
        'address': ', '.join(x for x in (prop.address, prop.city, prop.postal_code) if x),
        'wifi_name': access.wifi_name if access else '',
        'wifi_password': access.wifi_password if access else '',
        'door_code': access.door_code if access else '',
        'check_in_instructions': access.check_in_instructions if access else '',
        'house_rules': access.house_rules if access else '',
        'booking_ref': reservation.channel_booking_ref or str(reservation.pk)[:8].upper(),
    }


def render(text, context):
    """Bilinmeyen {değişken}'ler olduğu gibi kalır; süslü parantez hataları gönderimi bozmaz."""
    try:
        return (text or '').format_map(_SafeDict(context))
    except (ValueError, IndexError, AttributeError):
        result = text or ''
        for key, value in context.items():
            result = result.replace('{' + key + '}', str(value))
        return result


# --------------------------------------------------------------------------- schedule
def choose_templates(reservation):
    """Tetikleyici başına bir şablon: misafir dili > varsayılan dil > ilk aktif."""
    by_trigger = {}
    for tpl in MessageTemplate.objects.filter(is_active=True).order_by('created_at'):
        by_trigger.setdefault(tpl.trigger, []).append(tpl)
    chosen = []
    preferred = [reservation.guest_language, settings.MESSAGE_DEFAULT_LANGUAGE]
    for templates in by_trigger.values():
        pick = next((t for lang in preferred if lang for t in templates if t.language == lang), templates[0])
        chosen.append(pick)
    return chosen


def compute_send_at(template, reservation, now):
    """(send_at, too_late) döndürür."""
    tz = property_tz()
    ci, co = reservation.check_in, reservation.check_out
    hours = timedelta(hours=template.offset_hours)
    if template.trigger == Trigger.BOOKING_CONFIRMED:
        return now + hours, False
    if template.trigger == Trigger.BEFORE_CHECK_IN:
        send_at, deadline = ci - hours, ci
    elif template.trigger == Trigger.CHECK_IN_DAY:
        day = ci.astimezone(tz).date()
        send_at = datetime.combine(day, template.send_time or DEFAULT_SEND_TIMES[template.trigger], tzinfo=tz)
        deadline = co
    elif template.trigger == Trigger.CHECK_OUT_MORNING:
        day = co.astimezone(tz).date()
        send_at = datetime.combine(day, template.send_time or DEFAULT_SEND_TIMES[template.trigger], tzinfo=tz)
        deadline = co + timedelta(hours=12)
    else:  # AFTER_CHECK_OUT
        send_at, deadline = co + hours, co + hours + timedelta(hours=48)
    if send_at >= now:
        return send_at, False
    return (now, False) if now < deadline else (send_at, True)


def schedule_for_reservation(reservation, now=None):
    """Rezervasyonun planlı mesajlarını güncel durumuyla eşitler (idempotent)."""
    now = now or timezone.now()
    pending = ScheduledMessage.objects.filter(reservation=reservation, status=ScheduledMessage.Status.PENDING)
    if reservation.status in ('cancelled', 'no_show', 'pending'):
        pending.update(status=ScheduledMessage.Status.CANCELLED, updated_at=now)
        return
    if reservation.status != 'confirmed':
        return  # completed: planlananlar (ör. yorum isteği) aynen gider, yenisi eklenmez
    for template in choose_templates(reservation):
        existing = ScheduledMessage.objects.filter(reservation=reservation, template__trigger=template.trigger).first()
        if existing and existing.status in (ScheduledMessage.Status.SENT, ScheduledMessage.Status.SENDING,
                                            ScheduledMessage.Status.FAILED):
            continue
        if existing and existing.template_id != template.id and existing.status == ScheduledMessage.Status.PENDING:
            existing.template = template  # dil değişti
        if existing and existing.template.trigger == Trigger.BOOKING_CONFIRMED \
                and existing.status == ScheduledMessage.Status.PENDING:
            continue  # onay mesajının zamanı ilk planlamada sabitlenir
        send_at, too_late = compute_send_at(template, reservation, now)
        status = ScheduledMessage.Status.SKIPPED if too_late else ScheduledMessage.Status.PENDING
        if existing:
            if existing.status == ScheduledMessage.Status.SKIPPED and too_late:
                continue
            existing.send_at, existing.status, existing.error = send_at, status, ''
            existing.save(update_fields=['template', 'send_at', 'status', 'error', 'updated_at'])
        else:
            try:
                with transaction.atomic():
                    ScheduledMessage.objects.create(
                        reservation=reservation, template=template, send_at=send_at, status=status,
                    )
            except IntegrityError:
                pass  # eşzamanlı planlama: kayıt zaten var


# --------------------------------------------------------------------------- inbox helpers
def channel_of(reservation):
    if uses_channel_manager(reservation):
        return reservation.source
    return 'email'


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
        from django.db.models import F
        fields['unread_count'] = F('unread_count') + unread_increment
    if fields:
        Conversation.objects.filter(pk=conversation.pk).update(**fields)


def record_outgoing(reservation, body, *, source, external_id=None, status=Message.Status.SENT,
                    error='', scheduled_message=None, user=None):
    conversation = get_conversation(reservation)
    message = Message.objects.create(
        conversation=conversation, direction=Message.Direction.OUT, source=source, body=body,
        sent_at=timezone.now(), external_id=external_id or None, status=status, error=error[:1000],
        scheduled_message=scheduled_message, sent_by=user,
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


# --------------------------------------------------------------------------- send due
def send_scheduled(message_id, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        sm = (
            ScheduledMessage.objects.select_for_update(skip_locked=True)
            .filter(pk=message_id, status=ScheduledMessage.Status.PENDING, send_at__lte=now).first()
        )
        if sm is None:
            return 'skipped'
        sm.status = ScheduledMessage.Status.SENDING
        sm.attempts += 1
        sm.save(update_fields=['status', 'attempts', 'updated_at'])

    sm = ScheduledMessage.objects.select_related('reservation__guest', 'reservation__property', 'template').get(pk=sm.pk)
    reservation = sm.reservation
    if reservation.status not in ('confirmed', 'completed'):
        sm.status = ScheduledMessage.Status.CANCELLED
        sm.save(update_fields=['status', 'updated_at'])
        return 'cancelled'
    context = template_context(reservation)
    subject, body = render(sm.template.subject, context), render(sm.template.body, context)
    sender = sender_for(reservation)
    try:
        external_id = sender.send(reservation, subject, body)
    except Exception as exc:
        error = f'{exc.__class__.__name__}: {str(exc)[:500]}'
        retry = sm.attempts < MAX_ATTEMPTS and not isinstance(exc, (MessageSendError, NotImplementedError))
        sm.status = ScheduledMessage.Status.PENDING if retry else ScheduledMessage.Status.FAILED
        sm.send_at = now + RETRY_DELAY if retry else sm.send_at
        sm.error, sm.channel = error, sender.channel
        sm.save(update_fields=['status', 'send_at', 'error', 'channel', 'updated_at'])
        if not retry:
            record_outgoing(reservation, body, source=Message.Source.AUTO, status=Message.Status.FAILED,
                            error=error, scheduled_message=sm)
        return 'retry' if retry else 'failed'
    sm.status, sm.sent_at, sm.channel, sm.error = ScheduledMessage.Status.SENT, timezone.now(), sender.channel, ''
    sm.save(update_fields=['status', 'sent_at', 'channel', 'error', 'updated_at'])
    record_outgoing(reservation, body, source=Message.Source.AUTO, external_id=external_id, scheduled_message=sm)
    return 'sent'


def send_due_messages(now=None):
    now = now or timezone.now()
    ids = list(
        ScheduledMessage.objects.filter(status=ScheduledMessage.Status.PENDING, send_at__lte=now)
        .order_by('send_at').values_list('pk', flat=True)[:200]
    )
    summary = {}
    for pk in ids:
        result = send_scheduled(pk, now)
        summary[result] = summary.get(result, 0) + 1
    return summary
