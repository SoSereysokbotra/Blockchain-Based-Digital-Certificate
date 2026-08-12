"""
Background tasks (FR-2.5 – FR-2.10, FR-3.4).

Everything on-chain happens here, on the single-worker django-q2 cluster, and
never inside a request. A confirmation on Amoy takes seconds at best and
minutes when the network is busy; holding an HTTP worker open for that would
stall the whole site under a handful of concurrent issuances.

These functions are called by name from a queue, so they must never raise: an
uncaught exception in a django-q2 task is recorded as a failed task and the
certificate would sit PENDING with nothing explaining why. Failures are caught,
written to the certificate and to BlockchainInteractionLog, and swallowed.
"""
from __future__ import annotations

import logging

from django.utils import timezone

from blockchain.logging_utils import InteractionType, record_interaction
from blockchain.service import BlockchainError, get_service

from .models import Certificate, CertificateStatus, RevocationLog

logger = logging.getLogger(__name__)


def process_issuance(certificate_id: str) -> bool:
    """
    Anchor a certificate's hash on-chain and promote it to VALID (FR-2.5–2.8).

    The status only moves to VALID after a receipt confirms, which is what
    makes FR-2.7 true: a certificate that is not anchored never verifies.
    """
    certificate = Certificate.objects.filter(certificate_id=certificate_id).first()
    if certificate is None:
        logger.error('process_issuance: no certificate %s', certificate_id)
        return False

    if certificate.status not in (CertificateStatus.PENDING, CertificateStatus.FAILED):
        # Already resolved — a duplicate queue entry, not an error.
        logger.info(
            'process_issuance: %s is %s, nothing to do',
            certificate_id, certificate.status,
        )
        return False

    if not certificate.certificate_hash:
        from .hashing import compute_certificate_hash

        certificate.certificate_hash = compute_certificate_hash(certificate)
        certificate.save(update_fields=['certificate_hash', 'updated_at'])

    Certificate.objects.filter(pk=certificate.pk).update(
        issuance_attempts=certificate.issuance_attempts + 1
    )

    service = get_service()

    try:
        with record_interaction(
            InteractionType.ISSUE, certificate=certificate
        ) as entry:
            if not service.is_configured():
                raise BlockchainError(
                    'Blockchain is not configured (BLOCKCHAIN_RPC_URL, '
                    'BLOCKCHAIN_CONTRACT_ADDRESS and '
                    'BLOCKCHAIN_ISSUER_PRIVATE_KEY must all be set).'
                )

            result = service.issue_certificate(
                certificate.certificate_id, certificate.certificate_hash
            )
            entry['tx_hash'] = result.tx_hash
            entry['block_number'] = result.block_number
            entry['gas_used'] = result.gas_used

    except Exception as exc:  # noqa: BLE001 — recorded, never propagated
        logger.exception('Issuance failed for %s', certificate_id)
        certificate.status = CertificateStatus.FAILED
        certificate.failure_reason = str(exc)[:2000]
        certificate.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return False

    certificate.blockchain_tx_hash = result.tx_hash
    certificate.blockchain_block_number = result.block_number
    certificate.anchored_at = timezone.now()
    certificate.failure_reason = ''
    # A certificate whose expiry has already passed goes straight to EXPIRED
    # rather than briefly claiming to be VALID.
    certificate.status = (
        CertificateStatus.EXPIRED if certificate.is_past_expiry
        else CertificateStatus.VALID
    )
    certificate.save(update_fields=[
        'blockchain_tx_hash', 'blockchain_block_number', 'anchored_at',
        'status', 'failure_reason', 'updated_at',
    ])

    logger.info(
        'Anchored %s in block %s (tx %s)',
        certificate_id, result.block_number, result.tx_hash,
    )

    if certificate.status == CertificateStatus.VALID:
        _queue_issuance_email(certificate)

    return True


def process_revocation(certificate_id: str) -> bool:
    """
    Set the on-chain revoked flag, then mirror it in the database (FR-3.4, FR-3.5).

    Ordering matters: the chain is authoritative for `revoked`, so the database
    is only updated after the transaction confirms. Flipping the row first would
    show a certificate as revoked while it still verified as valid to anyone
    reading the contract directly.
    """
    certificate = Certificate.objects.filter(certificate_id=certificate_id).first()
    if certificate is None:
        logger.error('process_revocation: no certificate %s', certificate_id)
        return False

    revocation = RevocationLog.objects.filter(certificate=certificate).first()
    if revocation is None:
        logger.error('process_revocation: no RevocationLog for %s', certificate_id)
        return False

    if certificate.status == CertificateStatus.REVOKED and revocation.confirmed_on_chain:
        return False

    service = get_service()

    try:
        with record_interaction(
            InteractionType.REVOKE, certificate=certificate
        ) as entry:
            if not service.is_configured():
                raise BlockchainError('Blockchain is not configured.')

            result = service.revoke_certificate(certificate.certificate_id)
            entry['tx_hash'] = result.tx_hash
            entry['block_number'] = result.block_number
            entry['gas_used'] = result.gas_used

    except Exception as exc:  # noqa: BLE001
        # A contract revert reaching here means the Django integration tried to
        # revoke something it does not own, or that was never anchored. Surface
        # it rather than reporting a silent success.
        logger.exception('Revocation failed for %s', certificate_id)
        revocation.failure_reason = str(exc)[:2000]
        revocation.confirmed_on_chain = False
        revocation.save(update_fields=['failure_reason', 'confirmed_on_chain'])
        return False

    revocation.blockchain_tx_hash = result.tx_hash
    revocation.confirmed_on_chain = True
    revocation.failure_reason = ''
    revocation.save(update_fields=[
        'blockchain_tx_hash', 'confirmed_on_chain', 'failure_reason',
    ])

    certificate.status = CertificateStatus.REVOKED
    certificate.save(update_fields=['status', 'updated_at'])

    # The public verification cache holds `revoked` for 60 seconds; drop it now
    # so the change is visible immediately rather than after the TTL (FR-5.9).
    from .verification import invalidate_revocation_cache

    invalidate_revocation_cache(certificate.certificate_id)

    logger.info('Revoked %s on-chain (tx %s)', certificate_id, result.tx_hash)
    return True


def flag_stale_pending() -> int:
    """
    Mark stuck issuances as retryable (FR-2.9).

    Scheduled every 10 minutes. A PENDING certificate older than
    STALE_PENDING_MINUTES means the worker died, the receipt never arrived, or
    the transaction was dropped. This does not auto-retry — re-submitting
    without a human looking could burn gas repeatedly against a permanent
    failure — it makes the certificate visibly actionable in the dashboard,
    which `is_retryable` already exposes on every list row.
    """
    from datetime import timedelta

    from django.conf import settings

    cutoff = timezone.now() - timedelta(minutes=settings.STALE_PENDING_MINUTES)
    stale = Certificate.objects.filter(
        status=CertificateStatus.PENDING, created_at__lt=cutoff
    )

    count = stale.count()
    if count:
        logger.warning(
            '%s certificate(s) stuck PENDING for over %s minutes: %s',
            count, settings.STALE_PENDING_MINUTES,
            ', '.join(stale.values_list('certificate_id', flat=True)[:20]),
        )
    return count


def expire_certificates() -> int:
    """Daily transition of past-expiry certificates to EXPIRED (FR-4.2.1)."""
    today = timezone.now().date()
    updated = Certificate.objects.filter(
        status=CertificateStatus.VALID, expiry_date__lt=today
    ).update(status=CertificateStatus.EXPIRED, updated_at=timezone.now())

    if updated:
        logger.info('Expired %s certificate(s)', updated)
    return updated


def _queue_issuance_email(certificate) -> None:
    """Hand off to the notification service (Phase 8)."""
    try:
        from django_q.tasks import async_task

        async_task(
            'notifications.tasks.send_certificate_issued',
            certificate.certificate_id,
        )
    except Exception:  # noqa: BLE001
        # A queueing problem must not undo a confirmed anchor.
        logger.exception(
            'Could not queue issuance email for %s', certificate.certificate_id
        )
