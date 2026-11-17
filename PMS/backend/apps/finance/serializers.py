from rest_framework import serializers

from apps.reservations.models import Reservation


class PaymentSerializer(serializers.ModelSerializer):
    """Rezervasyonun otomatik hesaplanan finans görünümü (Payments sayfası). Tamamen salt-okunur."""
    property_name = serializers.CharField(source='property.name', read_only=True)
    guest_name = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'property', 'property_name', 'guest', 'guest_name', 'source', 'status',
            'check_in', 'check_out', 'currency', 'channel_booking_ref', 'external_source_id',
            'total_price', 'channel_commission', 'commission_is_estimated', 'cleaning_fee', 'taxes',
            'net_amount',
        ]
        read_only_fields = fields

    def get_guest_name(self, obj):
        return f'{obj.guest.first_name} {obj.guest.last_name}'.strip()
