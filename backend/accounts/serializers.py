"""Request validation for the authentication endpoints."""
from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import CODE_LENGTH, Organization


class PasswordField(serializers.CharField):
    """
    Password input run through Django's validator chain (SRS 3.1.5).

    min_length is enforced here as well as by MinimumLengthValidator so the
    client gets a field-level error rather than a non-field one.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('write_only', True)
        kwargs.setdefault('min_length', 10)
        kwargs.setdefault('max_length', 128)
        kwargs.setdefault('style', {'input_type': 'password'})
        super().__init__(**kwargs)


def run_password_validators(password: str, user=None) -> None:
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc


class CodeField(serializers.CharField):
    """A 6-digit one-time code."""

    def __init__(self, **kwargs):
        kwargs.setdefault('min_length', CODE_LENGTH)
        kwargs.setdefault('max_length', CODE_LENGTH)
        kwargs.setdefault('trim_whitespace', True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not value.isdigit():
            raise serializers.ValidationError('Code must be numeric.')
        return value


class EmailField(serializers.EmailField):
    def __init__(self, **kwargs):
        kwargs.setdefault('max_length', 254)  # RFC 5321
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return super().to_internal_value(data).strip().lower()


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, trim_whitespace=True)
    email = EmailField()
    password = PasswordField()

    def validate_email(self, value):
        if Organization.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                'An account with this email already exists.'
            )
        return value

    def validate(self, data):
        # Run after the other fields so UserAttributeSimilarityValidator can
        # compare the password against the name and email being registered.
        run_password_validators(
            data['password'],
            user=Organization(email=data['email'], name=data['name']),
        )
        return data

    def create(self, validated_data):
        return Organization.objects.create_user(
            email=validated_data['email'],
            name=validated_data['name'],
            password=validated_data['password'],
        )


class LoginSerializer(serializers.Serializer):
    email = EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class EmailOnlySerializer(serializers.Serializer):
    """Used by resend-verification and request-password-reset."""

    email = EmailField()


class VerifyEmailSerializer(serializers.Serializer):
    """
    Email is required alongside the code.

    Looking a code up by itself across all accounts would mean a six-digit
    guess could verify *whichever* account happened to hold that code, and no
    per-account rate limit could see it coming. Binding the code to an email
    turns it back into a 1-in-a-million guess against one specific account.
    """

    email = EmailField()
    code = CodeField()


class VerifyPasswordResetSerializer(serializers.Serializer):
    email = EmailField()
    code = CodeField()


class ResetPasswordSerializer(serializers.Serializer):
    email = EmailField()
    code = CodeField()
    new_password = PasswordField()

    def validate(self, data):
        run_password_validators(data['new_password'])
        return data


class OrganizationSerializer(serializers.ModelSerializer):
    """
    Safe representation of the signed-in organisation.

    Explicit allow-list, not `exclude`: adding a field to the model must never
    publish it by accident, and `password` lives on this model.
    """

    class Meta:
        model = Organization
        fields = ['id', 'name', 'email', 'wallet_address', 'is_verified', 'created_at']
        read_only_fields = fields
