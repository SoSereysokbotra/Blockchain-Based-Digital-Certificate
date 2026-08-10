from rest_framework import serializers
from django.utils import timezone
from .models import Organization


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=10, write_only=True)

    def validate_email(self, value):
        if Organization.objects.filter(email=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def create(self, validated_data):
        return Organization.objects.create_user(
            email=validated_data['email'],
            name=validated_data['name'],
            password=validated_data['password'],
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class VerifyEmailSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyPasswordResetSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(min_length=10, write_only=True)
