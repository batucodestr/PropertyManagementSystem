from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.reservations.models import Reservation
from . import services
from .models import Conversation, MessageTemplate, ScheduledMessage
from .senders import MessageSendError
from .serializers import (
    TEMPLATE_VARIABLES, ConversationSerializer, MessageSerializer, MessageTemplateSerializer, ReplySerializer,
    ScheduledMessageSerializer,
)


class MessageTemplateViewSet(viewsets.ModelViewSet):
    queryset = MessageTemplate.objects.order_by('trigger', 'language', 'name')
    serializer_class = MessageTemplateSerializer
    filterset_fields = ['trigger', 'language', 'is_active']
    search_fields = ['name', 'subject', 'body']

    @action(detail=False, methods=['get'])
    def variables(self, request):
        return Response({'variables': TEMPLATE_VARIABLES, 'triggers': MessageTemplate.Trigger.choices})

    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        """Şablonu gerçek bir rezervasyonla işler (göndermez). Body: {reservation: <uuid>}"""
        template = self.get_object()
        reservation = get_object_or_404(
            Reservation.objects.select_related('property', 'guest'), pk=request.data.get('reservation'),
        )
        context = services.template_context(reservation)
        return Response({
            'subject': services.render(template.subject, context),
            'body': services.render(template.body, context),
        })


class ScheduledMessageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ScheduledMessage.objects.select_related('template').order_by('send_at')
    serializer_class = ScheduledMessageSerializer
    filterset_fields = ['reservation', 'status', 'template']

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        updated = ScheduledMessage.objects.filter(pk=pk, status=ScheduledMessage.Status.PENDING).update(
            status=ScheduledMessage.Status.CANCELLED,
        )
        if not updated:
            return Response({'detail': 'Only pending messages can be cancelled.'}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(self.get_object()).data)


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = (
        Conversation.objects.select_related('reservation__guest', 'reservation__property')
        .order_by('-last_message_at', '-created_at')
    )
    serializer_class = ConversationSerializer
    filterset_fields = ['channel', 'reservation']
    search_fields = ['reservation__guest__first_name', 'reservation__guest__last_name', 'reservation__property__name']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('unread') in ('1', 'true'):
            qs = qs.filter(unread_count__gt=0)
        if self.request.query_params.get('property'):
            qs = qs.filter(reservation__property_id=self.request.query_params['property'])
        return qs.filter(Q(last_message_at__isnull=False))

    @action(detail=False, methods=['post'], url_path='for-reservation')
    def for_reservation(self, request):
        """Rezervasyonun konuşmasını getirir/oluşturur (rezervasyon detayından 'Mesaj gönder')."""
        reservation = get_object_or_404(Reservation, pk=request.data.get('reservation'))
        conversation = services.get_conversation(reservation)
        return Response(ConversationSerializer(conversation).data)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conversation = get_object_or_404(Conversation, pk=pk)
        return Response(MessageSerializer(conversation.messages.select_related('sent_by'), many=True).data)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        conversation = get_object_or_404(Conversation.objects.select_related('reservation'), pk=pk)
        serializer = ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = services.send_reply(conversation, serializer.validated_data['body'], user=request.user)
        except MessageSendError as exc:
            return Response({'detail': f'Message could not be sent: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        conversation = get_object_or_404(Conversation.objects.select_related('reservation'), pk=pk)
        return Response({'marked': services.mark_conversation_read(conversation)})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        total = sum(Conversation.objects.filter(unread_count__gt=0).values_list('unread_count', flat=True))
        return Response({'unread': total})
