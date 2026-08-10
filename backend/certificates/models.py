import uuid
from django.db import models
from django.conf import settings


class CertificateStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    VALID = 'VALID', 'Valid'
    EXPIRED = 'EXPIRED', 'Expired'
    REVOKED = 'REVOKED', 'Revoked'
    FAILED = 'FAILED', 'Failed'


class Certificate(models.Model):
    # Identity
    certificate_id = models.CharField(
        max_length=100,
        unique=True,
        editable=False
    )
    organization = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='certificates'
    )

    # Recipient information
    recipient_name = models.CharField(max_length=200)
    recipient_email = models.EmailField()

    # Certificate details
    course_title = models.CharField(max_length=200)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.PENDING
    )

    # Blockchain record
    certificate_hash = models.CharField(max_length=66, blank=True)   # SHA-256 hex
    blockchain_tx_hash = models.CharField(max_length=66, blank=True)

    # PDF
    pdf_url = models.CharField(max_length=500, blank=True)

    # Idempotency — store key from header to prevent duplicates
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'certificates'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.certificate_id} — {self.recipient_name}'

    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = f'CERT-{uuid.uuid4().hex[:12].upper()}'
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.expiry_date and timezone.now().date() > self.expiry_date:
            return True
        return False


class RevocationLog(models.Model):
    certificate = models.OneToOneField(
        Certificate,
        on_delete=models.CASCADE,
        related_name='revocation'
    )
    reason = models.TextField()
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='revocations'
    )
    revoked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revocation_logs'

    def __str__(self):
        return f'Revocation: {self.certificate.certificate_id}'
