"""
Certificate creation orchestration (FR-2.1 – FR-2.3, FR-2.2.1).

The write ordering here is the load-bearing part:

    1. persist the row as PENDING
    2. compute the canonical hash and store it
    3. render the PDF
    4. enqueue the on-chain anchor

The row exists before anything can fail. If PDF rendering or the chain call
falls over, the certificate is a recoverable PENDING/FAILED record that can be
retried, rather than work that vanished. Doing it the other way round — anchor
first, save second — would leave hashes on an immutable ledger with no database
row to explain them.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

from .hashing import compute_certificate_hash
from .models import Certificate, CertificateStatus
from .pdf import generate_and_store_pdf

logger = logging.getLogger(__name__)


class CertificateService:
    """Creates certificates for one organisation."""

    def __init__(self, organization):
        self.organization = organization

    # ─── Creation ─────────────────────────────────────────────────────────────

    def create(self, validated_data: dict, *, idempotency_key: str | None = None):
        """
        Create a certificate and return (certificate, created).

        `created` is False when an idempotency key matched an existing record,
        which lets the view answer a retry with the original certificate
        instead of issuing a duplicate (FR-2.2.1).
        """
        if idempotency_key:
            existing = self.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info(
                    'Idempotency key %s matched existing certificate %s',
                    idempotency_key, existing.certificate_id,
                )
                return existing, False

        try:
            with transaction.atomic():
                certificate = Certificate.objects.create(
                    organization=self.organization,
                    recipient_name=validated_data['recipient_name'],
                    recipient_email=validated_data['recipient_email'],
                    course_title=validated_data['course_title'],
                    issue_date=validated_data['issue_date'],
                    expiry_date=validated_data.get('expiry_date'),
                    status=CertificateStatus.PENDING,
                    idempotency_key=idempotency_key or None,
                )
                # Computed after save so certificate_id is final — the ID is
                # part of the hashed payload.
                certificate.certificate_hash = compute_certificate_hash(certificate)
                certificate.save(update_fields=['certificate_hash', 'updated_at'])
        except IntegrityError:
            # Two concurrent requests carrying the same key: the loser reads
            # back the winner's row rather than failing the caller.
            existing = self.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing, False
            raise

        self.attach_pdf(certificate)
        return certificate, True

    def find_by_idempotency_key(self, key: str | None):
        if not key:
            return None
        return Certificate.objects.filter(
            organization=self.organization, idempotency_key=key
        ).first()

    # ─── Artefacts ────────────────────────────────────────────────────────────

    @staticmethod
    def attach_pdf(certificate) -> bool:
        """
        Render the PDF and record its path and digest.

        A rendering failure is logged and swallowed rather than raised: the
        certificate's hash is already computed and can still be anchored and
        verified, so losing the PDF should degrade the deliverable, not the
        credential. The retry endpoint regenerates it.
        """
        try:
            relative_path, digest = generate_and_store_pdf(certificate)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                'PDF generation failed for %s', certificate.certificate_id
            )
            certificate.failure_reason = f'PDF generation failed: {exc}'
            certificate.save(update_fields=['failure_reason', 'updated_at'])
            return False

        certificate.pdf_url = relative_path
        certificate.pdf_sha256 = digest
        certificate.save(update_fields=['pdf_url', 'pdf_sha256', 'updated_at'])
        return True

    # ─── Queueing ─────────────────────────────────────────────────────────────

    @staticmethod
    def enqueue_issuance(certificate) -> None:
        """Hand the on-chain anchor to the single-concurrency worker (Phase 5)."""
        from django_q.tasks import async_task

        async_task('certificates.tasks.process_issuance', certificate.certificate_id)
        logger.info('Queued issuance for %s', certificate.certificate_id)
