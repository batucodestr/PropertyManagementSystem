from rest_framework import serializers

from .models import Conversation, Message

class MessageSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'direction', 'source', 'body', 'sent_at', 'status', 'is_read', 'error', 'sent_by_name']
        read_only_fields = fields

    def get_sent_by_name(self, obj):
        return (obj.sent_by.get_full_name() or obj.sent_by.username) if obj.sent_by else None


class ConversationSerializer(serializers.ModelSerializer):
    guest_name = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='reservation.property.name', read_only=True)
    check_in = serializers.DateTimeField(source='reservation.check_in', read_only=True)
    check_out = serializers.DateTimeField(source='reservation.check_out', read_only=True)
    reservation_status = serializers.CharField(source='reservation.status', read_only=True)
    source = serializers.CharField(source='reservation.source', read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'reservation', 'channel', 'source', 'guest_name', 'property_name', 'check_in', 'check_out',
                  'reservation_status', 'last_message_at', 'last_message_preview', 'unread_count']
        read_only_fields = fields

    def get_guest_name(self, obj):
        guest = obj.reservation.guest
        return f'{guest.first_name} {guest.last_name}'.strip()


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)
