from rest_framework import serializers
from .models import DailyRate, Property, PropertyAccessInfo, PropertyImage, SeasonalRate
from .validate import validate_property_data

class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = '__all__'

    def validate_property(self, prop):
        # Veritabanı/disk tasarrufu: mülk başına en fazla 1 resim.
        qs = prop.images.all()
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Bu mülk için zaten bir resim var. Önce mevcut resmi silin.')
        return prop


class PropertySerializer(serializers.ModelSerializer):
    images = PropertyImageSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = '__all__'

    def validate(self, data):
        validate_property_data(data)
        return data


class PublicPropertySerializer(serializers.ModelSerializer):
    """Tanıtım sitesine açılan, salt-okunur mülk görünümü.

    Kişisel/operasyonel alanlar (telefon, e-posta, açık adres, posta kodu)
    bilerek dışarıda bırakılır. Görsel, sitenin kendi sunucusu üzerinden
    proxy'lenebilsin diye host'tan bağımsız göreli yol (/media/...) olarak döner.
    """

    image = serializers.SerializerMethodField()
    image_alt = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'id', 'name', 'description', 'city', 'country',
            'max_guests', 'bedroom_count', 'bed_count', 'bathroom_count',
            'area', 'base_price', 'image', 'image_alt', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @staticmethod
    def _first_image(obj):
        # prefetch_related('images') ile gelen önbelleği kullanır, ek sorgu atmaz.
        images = list(obj.images.all())
        return images[0] if images else None

    def get_image(self, obj):
        img = self._first_image(obj)
        if not img or not img.image:
            return None
        return img.image.url

    def get_image_alt(self, obj):
        img = self._first_image(obj)
        return (img.alt_text if img else '') or obj.name


def _check_min_stay(data):
    if data.get('min_stay') is not None and data['min_stay'] < 1:
        raise serializers.ValidationError({'min_stay': 'Minimum stay must be at least 1 night.'})


class SeasonalRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeasonalRate
        fields = '__all__'

    def validate(self, data):
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})
        for field in ('nightly_price', 'weekend_price'):
            if data.get(field) is not None and data[field] < 0:
                raise serializers.ValidationError({field: 'This value cannot be negative.'})
        _check_min_stay(data)
        return data


class DailyRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyRate
        fields = '__all__'

    def validate(self, data):
        if data.get('price') is not None and data['price'] < 0:
            raise serializers.ValidationError({'price': 'This value cannot be negative.'})
        _check_min_stay(data)
        return data


class BulkDailyRateSerializer(serializers.Serializer):
    """Bir tarih aralığına toplu gün fiyatı / min stay / kapalı uygular ya da override'ları temizler."""
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=0)
    min_stay = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    closed = serializers.BooleanField(required=False, default=False)
    clear = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if data['date_to'] < data['date_from']:
            raise serializers.ValidationError({'date_to': 'End date cannot be before start date.'})
        if (data['date_to'] - data['date_from']).days > 400:
            raise serializers.ValidationError({'date_to': 'The range can be at most 400 days.'})
        return data



class PropertyAccessInfoSerializer(serializers.ModelSerializer):
    """Hassas: sadece yetkili personel uçlarında. PublicPropertySerializer bu modele asla bağlanmaz."""

    class Meta:
        model = PropertyAccessInfo
        fields = ['wifi_name', 'wifi_password', 'door_code', 'check_in_instructions', 'house_rules', 'updated_at']
        read_only_fields = ['updated_at']
