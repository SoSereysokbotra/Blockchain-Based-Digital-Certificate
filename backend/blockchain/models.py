"""Audit log of every chain interaction (FR-2.10)."""
from __future__ import annotations

from django.db import models


class InteractionType(models.TextChoices):
    ISSUE = 'ISSUE', 'Issue certificate'
    REVOKE = 'REVOKE', 'Revoke certificate'
    READ = 'READ', 'Read certificate'


class BlockchainInteractionLog(models.Model):
    """
    One row per attempt — successful or not.

    FR-2.10 requires this to record failures as well as successes, so a failed
    issuance can be explained after the fact rather than only observed as a
    FAILED status with no context.
    """

    certificate = models.ForeignKey(
        'certificates.Certificate',
        on_delete=models.CASCADE,
        related_name='blockchain_interactions',
        null=True,
        blank=True,
    )
    # Named `certificate_public_id` rather than `certificate_id`, which Django
    # reserves as the FK's attname.
    certificate_public_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text='Denormalised BCIP certificate ID, kept for audit readability.',
    )

    interaction_type = models.CharField(
        max_length=10,
        choices=InteractionType.choices,
        db_index=True,
    )
    succeeded = models.BooleanField(default=False, db_index=True)

    tx_hash = models.CharField(max_length=66, blank=True)
    block_number = models.BigIntegerField(null=True, blank=True)
    gas_used = models.BigIntegerField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'blockchain_interaction_logs'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['certificate', '-created_at'])]

    def __str__(self):
        outcome = 'ok' if self.succeeded else 'FAILED'
        return f'{self.interaction_type} {self.certificate_public_id} — {outcome}'
