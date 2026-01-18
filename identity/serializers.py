from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import AnonymousProfile

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    ghost_id = serializers.UUIDField(source='ghost_profile.ghost_id', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'ghost_id', 'created_at']
        read_only_fields = ['id', 'email', 'ghost_id', 'created_at']

class AnonymousProfileSerializer(serializers.ModelSerializer):
    is_claimed = serializers.BooleanField(source='user_id', read_only=True)
    
    class Meta:
        model = AnonymousProfile
        fields = ['ghost_id', 'created_at', 'is_soft_deleted', 'is_claimed']

class OTPSendSerializer(serializers.Serializer):
    email = serializers.EmailField()

class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    ghost_id = serializers.UUIDField()
