from django.contrib.auth.models import User
from rest_framework import serializers

from .roles import role_of


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    groups = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'email', 'groups', 'role', 'is_active']
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_role(self, obj):
        return role_of(obj)
