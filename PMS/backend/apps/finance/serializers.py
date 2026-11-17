from django.utils import timezone
from rest_framework import serializers

from apps.reservations.models import Reservation
from .models import FinancialTransaction, RecurringExpense

Category = FinancialTransaction.Category
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
RECEIPT_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic')


class FinancialTransactionSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    category_label = serializers.CharField(source='get_category_display', read_only=True)
    is_automatic = serializers.SerializerMethodField()

    class Meta:
        model = FinancialTransaction
        fields = '__all__'
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'housekeeping_task', 'general_task', 'recurring_expense',
        ]

    def get_is_automatic(self, obj):
        return bool(obj.category == Category.RESERVATION or obj.housekeeping_task_id or obj.general_task_id)

    def validate_transaction_type(self, value):
        if value not in [choice[0] for choice in FinancialTransaction.TransactionType.choices]:
            raise serializers.ValidationError("Invalid transaction type.")
        return value

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_currency(self, value):
        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter code.")
        return value.upper()

    def validate_receipt(self, value):
        if value is None:
            return value
        if value.size > MAX_RECEIPT_BYTES:
            raise serializers.ValidationError("Receipt must be 10 MB or smaller.")
        if not value.name.lower().endswith(RECEIPT_EXTENSIONS):
            raise serializers.ValidationError("Receipt must be a PDF or an image.")
        return value

    def validate(self, data):
        if self.instance is not None and self.get_is_automatic(self.instance):
            raise serializers.ValidationError(
                "This transaction is managed automatically (reservation / task). Edit its source instead."
            )
        category = data.get('category', getattr(self.instance, 'category', None))
        tx_type = data.get('transaction_type', getattr(self.instance, 'transaction_type', None))
        if category == Category.RESERVATION:
            raise serializers.ValidationError({'category': "Reservation income is created automatically."})
        if category and tx_type:
            is_income_category = category in FinancialTransaction.INCOME_CATEGORIES
            if (tx_type == 'income') != is_income_category:
                raise serializers.ValidationError({'category': "Category does not match the transaction type."})
        return data


class RecurringExpenseSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    category_label = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = RecurringExpense
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        category = data.get('category', getattr(self.instance, 'category', None))
        if category in FinancialTransaction.INCOME_CATEGORIES:
            raise serializers.ValidationError({'category': "Choose an expense category."})
        day = data.get('day_of_month', getattr(self.instance, 'day_of_month', 1))
        if not 1 <= day <= 28:
            raise serializers.ValidationError({'day_of_month': "Day must be between 1 and 28."})
        if data.get('amount') is not None and data['amount'] <= 0:
            raise serializers.ValidationError({'amount': "Amount must be greater than zero."})
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': "End date cannot be before start date."})
        return data


class PaymentSerializer(serializers.ModelSerializer):
    """Rezervasyonun finans görünümü (Payments sayfası). Sadece finans alanları yazılabilir."""
    property_name = serializers.CharField(source='property.name', read_only=True)
    guest_name = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'property', 'property_name', 'guest', 'guest_name', 'source', 'status',
            'check_in', 'check_out', 'currency', 'channel_booking_ref', 'external_source_id',
            'total_price', 'channel_commission', 'commission_is_estimated', 'cleaning_fee', 'taxes',
            'net_amount', 'payout_status', 'payout_date',
        ]
        read_only_fields = [
            'id', 'property', 'property_name', 'guest', 'guest_name', 'source', 'status',
            'check_in', 'check_out', 'currency', 'channel_booking_ref', 'external_source_id',
            'total_price', 'commission_is_estimated', 'net_amount',
        ]

    def get_guest_name(self, obj):
        return f'{obj.guest.first_name} {obj.guest.last_name}'.strip()

    def validate(self, data):
        for field in ('channel_commission', 'cleaning_fee', 'taxes'):
            if data.get(field) is not None and data[field] < 0:
                raise serializers.ValidationError({field: "This value cannot be negative."})
        if 'channel_commission' in data:
            data['commission_is_estimated'] = data['channel_commission'] is None
        status = data.get('payout_status')
        if status == Reservation.PayoutStatus.PAID and not data.get('payout_date'):
            data['payout_date'] = getattr(self.instance, 'payout_date', None) or timezone.localdate()
        elif status == Reservation.PayoutStatus.PENDING:
            data['payout_date'] = None
        return data
