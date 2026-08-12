"""
Certificate lifecycle models (SRS 6.2, 6.3).

Everything a verifier sees comes from this table. The blockchain stores only
`certificate_hash`; PostgreSQL remains authoritative for content, and the chain
is authoritative for integrity and for the revoked flag (SRS 5.4 Authority Rule).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class CertificateStatus(models.TextChoices):
    # Row written, hash computed, on-chain anchor not yet confirmed.
    PENDING = 'PENDING', 'Pending'
    # Anchor confirmed. The only state in which a certificate verifies.
    VALID = 'VALID', 'Valid'
    # Past expiry_date. Set by the daily expiration job (FR-4.2.1).
    EXPIRED = 'EXPIRED', 'Expired'
    # Revoked by the issuer; terminal (FR-4.4).
    REVOKED = 'REVOKED', 'Revoked'
    # Anchoring failed. Retryable (FR-2.9).
    FAILED = 'FAILED', 'Failed'


def generate_certificate_id() -> str:
    return f'CERT-{uuid.uuid4().hex[:12].upper()}'


class Certificate(models.Model):
    certificate_id = models.CharField(
        max_length=100,
        unique=True,
        editable=False,
        default=generate_certificate_id,
        help_text='Public identifier. Appears in the PDF, the QR code and the URL.',
    )
    organization = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='certificates',
    )

    recipient_name = models.CharField(max_length=200)
    recipient_email = models.EmailField(max_length=254)
    course_title = models.CharField(max_length=200)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.PENDING,
        db_index=True,
    )

    # ─── Integrity ────────────────────────────────────────────────────────────
    # sha256(canonical(cert)) as 0x + 64 hex chars — see certificates/hashing.py.
    # This is what gets anchored on-chain and what verification recomputes.
    certificate_hash = models.CharField(max_length=66, blank=True, db_index=True)
    # sha256 of the PDF bytes as delivered. Never anchored; lets a recipient
    # confirm the specific file they hold is the one that was generated.
    pdf_sha256 = models.CharField(max_length=66, blank=True)
    blockchain_tx_hash = models.CharField(max_length=66, blank=True)
    blockchain_block_number = models.BigIntegerField(null=True, blank=True)
    anchored_at = models.DateTimeField(null=True, blank=True)

    pdf_url = models.CharField(
        max_length=500,
        blank=True,
        help_text='Path relative to MEDIA_ROOT, e.g. pdfs/CERT-ABC123.pdf',
    )

    # Populated when status is FAILED so the dashboard can explain the failure
    # and the operator can decide whether retrying is worthwhile (FR-2.10).
    failure_reason = models.TextField(blank=True)
    issuance_attempts = models.PositiveSmallIntegerField(default=0)

    # FR-2.2.1: a client retrying a create with the same key must get the
    # original certificate back, not a second one. Scoped per organisation so
    # two tenants cannot collide on a shared key.
    idempotency_key = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'certificates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'idempotency_key'],
                condition=models.Q(idempotency_key__isnull=False),
                name='unique_idempotency_key_per_organization',
            ),
        ]

    def __str__(self):
        return f'{self.certificate_id} — {self.recipient_name}'

    @property
    def is_past_expiry(self) -> bool:
        return bool(self.expiry_date and timezone.now().date() > self.expiry_date)

    @property
    def is_retryable(self) -> bool:
        """
        FAILED, or PENDING for longer than the stale threshold (FR-2.9).

        A PENDING row older than the threshold means the worker died, the
        receipt never arrived, or the transaction was dropped — all cases where
        re-submitting is the right move.
        """
        from django.conf import settings as django_settings

        if self.status == CertificateStatus.FAILED:
            return True
        if self.status == CertificateStatus.PENDING:
            threshold = getattr(django_settings, 'STALE_PENDING_MINUTES', 10)
            age = timezone.now() - self.created_at
            return age.total_seconds() > threshold * 60
        return False


class RevocationLog(models.Model):
    """One row per revocation (SRS 6.3). A certificate is revoked at most once."""

    certificate = models.OneToOneField(
        Certificate,
        on_delete=models.CASCADE,
        related_name='revocation',
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='revocations',
    )
    reason = models.TextField()
    revoked_at = models.DateTimeField(auto_now_add=True)

    # Mirrors the issuance fields: the DB row is written first, then the
    # on-chain flag is set asynchronously and recorded here.
    blockchain_tx_hash = models.CharField(max_length=66, blank=True)
    confirmed_on_chain = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'revocation_logs'
        ordering = ['-revoked_at']

    def __str__(self):
        return f'Revocation of {self.certificate.certificate_id}'
