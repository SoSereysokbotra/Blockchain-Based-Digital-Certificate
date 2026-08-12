"""Delivery log for outbound email (SRS 6.4, FR-6.3)."""
from __future__ import annotations

from django.db import models


class NotificationStatus(models.TextChoices):
    SENT = 'SENT', 'Sent'
    FAILED = 'FAILED', 'Failed'


class NotificationKind(models.TextChoices):
    CERTIFICATE_ISSUED = 'CERTIFICATE_ISSUED', 'Certificate issued'
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION', 'Email verification'
    PASSWORD_RESET = 'PASSWORD_RESET', 'Password reset'


class NotificationLog(models.Model):
    """
    One row per send attempt, including resends (SRS 6.4: Certificate 1–N Log).

    `certificate` is nullable because authentication emails are logged here too
    and are not tied to a certificate.
    """

    certificate = models.ForeignKey(
        'certificates.Certificate',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    kind = models.CharField(
        max_length=32,
        choices=NotificationKind.choices,
        default=NotificationKind.CERTIFICATE_ISSUED,
    )
    recipient_email = models.EmailField(max_length=254, db_index=True)
    subject = models.CharField(max_length=300, blank=True)

    status = models.CharField(
        max_length=10,
        choices=NotificationStatus.choices,
        db_index=True,
    )
    error_message = models.TextField(blank=True)
    has_attachment = models.BooleanField(default=False)

    # 1 for the original send, incrementing for each manual resend (FR-6.3).
    attempt = models.PositiveSmallIntegerField(default=1)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-sent_at']
        indexes = [models.Index(fields=['certificate', '-sent_at'])]

    def __str__(self):
        return f'{self.get_kind_display()} → {self.recipient_email} ({self.status})'
