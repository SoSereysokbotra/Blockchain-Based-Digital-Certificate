from rest_framework import serializers
from django.utils import timezone
from .models import Certificate, RevocationLog


class CertificateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the paginated list endpoint."""
    class Meta:
        model = Certificate
        fields = ['certificate_id', 'recipient_name', 'issue_date', 'status']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Auto-expire: if expiry_date passed, report EXPIRED regardless of stored status
        if instance.status == 'VALID' and instance.is_expired:
            data['status'] = 'EXPIRED'
        return data


class CertificateDetailSerializer(serializers.ModelSerializer):
    """Full serializer for the detail endpoint."""
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
            'blockchain_tx_hash',
            'pdf_url',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.status == 'VALID' and instance.is_expired:
            data['status'] = 'EXPIRED'
        return data


class CertificateCreateSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(max_length=200)
    recipient_email = serializers.EmailField()
    course_title = serializers.CharField(max_length=200)
    issue_date = serializers.DateField()
    expiry_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, data):
        if data.get('expiry_date') and data['expiry_date'] <= data['issue_date']:
            raise serializers.ValidationError({'expiry_date': 'Expiry date must be after issue date.'})
        return data


class RevocationSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3)


class PublicVerifySerializer(serializers.ModelSerializer):
    """Serializer for the public verification endpoint response."""
    revocation_reason = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'certificate_id',
            'recipient_name',
            'course_title',
            'issue_date',
            'status',
            'blockchain_tx_hash',
            'revocation_reason',
        ]

    def get_revocation_reason(self, instance):
        try:
            return instance.revocation.reason
        except RevocationLog.DoesNotExist:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Determine verification outcome status
        if instance.status == 'VALID' and instance.is_expired:
            data['status'] = 'EXPIRED'
        return data
