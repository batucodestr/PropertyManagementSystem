from rest_framework import serializers
from .models import ChannelConnection, ChannelListing, SyncLog, WebhookEvent

class ChannelConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelConnection
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {'credentials': {'write_only': True}}

class ChannelListingSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source='connection.provider', read_only=True)

    class Meta:
        model = ChannelListing
        fields = [
            'id', 'provider', 'property', 'external_listing_id', 'external_room_id', 'external_url',
            'sync_enabled', 'sync_status', 'last_synced_at', 'last_error',
            'airbnb_markup_percent', 'booking_markup_percent', 'airbnb_connected', 'booking_connected',
            'created_at', 'updated_at',
        ]
        # Eşleme id'leri ve senkron durumu sadece servisler tarafından yazılır.
        read_only_fields = [
            'id', 'provider', 'property', 'external_listing_id', 'external_room_id',
            'sync_status', 'last_synced_at', 'last_error', 'created_at', 'updated_at',
        ]

    def validate(self, data):
        for field in ('airbnb_markup_percent', 'booking_markup_percent'):
            if field in data and not (0 <= data[field] <= 100):
                raise serializers.ValidationError({field: 'Markup must be between 0 and 100.'})
        return data

class SyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
