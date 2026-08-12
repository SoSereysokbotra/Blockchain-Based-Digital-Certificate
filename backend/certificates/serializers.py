"""Serialisers for the organisation-facing certificate endpoints."""
from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import Certificate, CertificateStatus
from .validators import validate_recipient_email, validate_safe_text


class CertificateCreateSerializer(serializers.Serializer):
    """FR-2.1, FR-2.1.1, FR-2.1.2 — validated certificate input."""

    recipient_name = serializers.CharField(
        max_length=settings.CERTIFICATE_NAME_MAX_LENGTH,
        trim_whitespace=True,
    )
    recipient_email = serializers.CharField(
        max_length=settings.CERTIFICATE_EMAIL_MAX_LENGTH,
    )
    course_title = serializers.CharField(
        max_length=settings.CERTIFICATE_TITLE_MAX_LENGTH,
        trim_whitespace=True,
    )
    issue_date = serializers.DateField()
    expiry_date = serializers.DateField(required=False, allow_null=True)

    def validate_recipient_name(self, value):
        return validate_safe_text(value, 'Recipient name')

    def validate_course_title(self, value):
        return validate_safe_text(value, 'Course title')

    def validate_recipient_email(self, value):
        return validate_recipient_email(value)

    def validate(self, data):
        expiry = data.get('expiry_date')
        if expiry and expiry <= data['issue_date']:
            raise serializers.ValidationError(
                {'expiry_date': 'Expiry date must be after the issue date.'}
            )
        return data


class CertificateListSerializer(serializers.ModelSerializer):
    """FR-3.1 — list rows."""

    is_retryable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'certificate_id',
            'recipient_name',
            'course_title',
            'issue_date',
            'expiry_date',
            'status',
            'is_retryable',
            'created_at',
        ]
        read_only_fields = fields


class CertificateDetailSerializer(serializers.ModelSerializer):
    """FR-3.3 — full detail, including the blockchain reference."""

    pdf_url = serializers.SerializerMethodField()
    explorer_url = serializers.SerializerMethodField()
    revocation_reason = serializers.SerializerMethodField()
    revoked_at = serializers.SerializerMethodField()
    is_retryable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'certificate_id',
            'recipient_name',
            'recipient_email',
            'course_title',
            'issue_date',
            'expiry_date',
            'status',
            'certificate_hash',
            'pdf_sha256',
            'blockchain_tx_hash',
            'blockchain_block_number',
            'anchored_at',
            'explorer_url',
            'pdf_url',
            'failure_reason',
            'is_retryable',
            'revocation_reason',
            'revoked_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_pdf_url(self, obj):
        if not obj.pdf_url:
            return None
        request = self.context.get('request')
        path = f'{settings.MEDIA_URL}{obj.pdf_url}'
        return request.build_absolute_uri(path) if request else path

    def get_explorer_url(self, obj):
        if not obj.blockchain_tx_hash:
            return None
        from blockchain.service import BlockchainService

        return BlockchainService.explorer_tx_url(obj.blockchain_tx_hash)

    def get_revocation_reason(self, obj):
        revocation = getattr(obj, 'revocation', None)
        return revocation.reason if revocation else None

    def get_revoked_at(self, obj):
        revocation = getattr(obj, 'revocation', None)
        return revocation.revoked_at if revocation else None


class CertificateCreatedSerializer(serializers.ModelSerializer):
    """202 response body for a create (FR-2.7)."""

    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = ['certificate_id', 'status', 'pdf_url', 'created_at']
        read_only_fields = fields

    def get_pdf_url(self, obj):
        if not obj.pdf_url:
            return None
        request = self.context.get('request')
        path = f'{settings.MEDIA_URL}{obj.pdf_url}'
        return request.build_absolute_uri(path) if request else path


class RevocationSerializer(serializers.Serializer):
    """FR-3.4 — revocation requires a reason."""

    reason = serializers.CharField(min_length=3, max_length=1000, trim_whitespace=True)

    def validate_reason(self, value):
        return validate_safe_text(value, 'Reason')
