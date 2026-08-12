"""
Public certificate verification (FR-5.1 – FR-5.9, SRS 7.6).

This is the part of BCIP that justifies the blockchain at all, so it is worth
being precise about what it does.

Two values are produced independently:

  * the hash recomputed *now* from the PostgreSQL row, and
  * the hash read from the smart contract, written at issuance and immutable.

If they disagree, the database was edited after issuance and the answer is
TAMPERED. Comparing the recomputed hash against `certificate.certificate_hash`
instead would be worthless: both live in the same row, so anyone who could
change the course title could change the stored hash to match, and every forged
certificate would still report VALID.

Authority rule (SRS 5.4): the chain decides `revoked` and integrity; the
database decides displayed content.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.ip import ratelimit_ip_key
from blockchain.service import BlockchainError, get_service

from .hashing import compute_certificate_hash, hashes_match
from .models import Certificate, CertificateStatus

logger = logging.getLogger(__name__)


class Outcome:
    VALID = 'VALID'
    EXPIRED = 'EXPIRED'
    REVOKED = 'REVOKED'
    TAMPERED = 'TAMPERED'
    NOT_FOUND = 'NOT_FOUND'
    # Distinct from TAMPERED on purpose: "we could not reach the chain" is not
    # the same claim as "this certificate was altered", and conflating them
    # would accuse an honest issuer of forgery during an RPC outage.
    UNVERIFIED = 'UNVERIFIED'


# ─── Cache (FR-5.9, NFR-1.10, NFR-2.1) ───────────────────────────────────────
#
# Backed by the same DatabaseCache configured in Phase 3.
#
# certHash and issuedAt cannot change once anchored, so they are cached for
# 30 days. `revoked` can change, so it gets a 60-second TTL *and* an explicit
# invalidation from the revocation task, which is what makes a revocation
# visible immediately rather than up to a minute later.

def _immutable_key(certificate_id: str) -> str:
    return f'onchain:immutable:{certificate_id}'


def _revoked_key(certificate_id: str) -> str:
    return f'onchain:revoked:{certificate_id}'


def invalidate_revocation_cache(certificate_id: str) -> None:
    cache.delete(_revoked_key(certificate_id))
    logger.info('Invalidated revoked-flag cache for %s', certificate_id)


def read_chain_record(certificate_id: str, *, use_cache: bool = True):
    """
    Fetch the on-chain record, preferring cache for the immutable half.

    Returns (record_dict, from_cache) or raises BlockchainError.
    """
    immutable = cache.get(_immutable_key(certificate_id)) if use_cache else None
    revoked = cache.get(_revoked_key(certificate_id)) if use_cache else None

    if immutable is not None and revoked is not None:
        return {**immutable, 'revoked': revoked}, True

    record = get_service().get_certificate(certificate_id)

    immutable = {
        'cert_hash': record.cert_hash,
        'issuer': record.issuer,
        'issued_at': record.issued_at,
        'exists': record.exists,
    }

    if use_cache and record.exists:
        # Only cache records that exist. Caching a miss for 30 days would hide
        # a certificate that is anchored moments later.
        cache.set(
            _immutable_key(certificate_id),
            immutable,
            settings.ONCHAIN_IMMUTABLE_CACHE_TTL,
        )
        cache.set(
            _revoked_key(certificate_id),
            record.revoked,
            settings.ONCHAIN_REVOKED_CACHE_TTL,
        )

    return {**immutable, 'revoked': record.revoked}, False


# ─── Resolution (SRS 7.6) ────────────────────────────────────────────────────

def verify_certificate(certificate_id: str, *, use_cache: bool = True) -> dict:
    """Resolve a certificate to one of the Outcome values plus its evidence."""
    certificate = (
        Certificate.objects
        .select_related('organization', 'revocation')
        .filter(certificate_id=certificate_id)
        .first()
    )

    if certificate is None:
        return {'status': Outcome.NOT_FOUND, 'certificate_id': certificate_id}

    recomputed = compute_certificate_hash(certificate)

    chain_record = None
    chain_error = None
    from_cache = False
    try:
        chain_record, from_cache = read_chain_record(
            certificate_id, use_cache=use_cache
        )
    except BlockchainError as exc:
        logger.warning('Chain read failed for %s: %s', certificate_id, exc)
        chain_error = str(exc)

    outcome = _resolve(certificate, recomputed, chain_record, chain_error)

    return _build_response(
        certificate=certificate,
        outcome=outcome,
        recomputed=recomputed,
        chain_record=chain_record,
        chain_error=chain_error,
        from_cache=from_cache,
    )


def _resolve(certificate, recomputed, chain_record, chain_error) -> str:
    """
    Decide the final status.

    Order is deliberate: integrity is checked before status, because a tampered
    record's own status field cannot be trusted to tell you it is revoked.
    """
    if certificate.status in (CertificateStatus.PENDING, CertificateStatus.FAILED):
        # Nothing anchored yet, so there is nothing to verify against.
        return Outcome.UNVERIFIED

    if chain_error is not None:
        return Outcome.UNVERIFIED

    if not chain_record['exists']:
        # The database claims this was issued but the ledger has no record of
        # it — a row inserted directly, bypassing issuance.
        return Outcome.TAMPERED

    if not hashes_match(recomputed, chain_record['cert_hash']):
        return Outcome.TAMPERED

    if chain_record['revoked']:
        return Outcome.REVOKED

    if certificate.is_past_expiry:
        return Outcome.EXPIRED

    return Outcome.VALID


def _build_response(*, certificate, outcome, recomputed, chain_record,
                    chain_error, from_cache) -> dict:
    from blockchain.service import BlockchainService

    revocation = getattr(certificate, 'revocation', None)

    payload = {
        'certificate_id': certificate.certificate_id,
        'status': outcome,
        'recipient_name': certificate.recipient_name,
        'course_title': certificate.course_title,
        'issue_date': certificate.issue_date.isoformat(),
        'expiry_date': (
            certificate.expiry_date.isoformat() if certificate.expiry_date else None
        ),
        'issuer_name': certificate.organization.name,
        'blockchain_tx_hash': certificate.blockchain_tx_hash or None,
        'explorer_url': (
            BlockchainService.explorer_tx_url(certificate.blockchain_tx_hash)
            if certificate.blockchain_tx_hash else None
        ),
        'revocation_reason': revocation.reason if revocation else None,
        'revoked_at': (
            revocation.revoked_at.isoformat()
            if revocation and outcome == Outcome.REVOKED else None
        ),
        'verified_at': timezone.now().isoformat(),
        'anchor': {
            'onchain_hash': chain_record['cert_hash'] if chain_record else None,
            'recomputed_hash': recomputed,
            'hash_matches': (
                hashes_match(recomputed, chain_record['cert_hash'])
                if chain_record else None
            ),
            'anchored_at': (
                certificate.anchored_at.isoformat() if certificate.anchored_at else None
            ),
            'served_from_cache': from_cache,
        },
    }

    if outcome == Outcome.TAMPERED:
        payload['warning'] = (
            'This certificate does not match the record anchored on the '
            'blockchain. Its details have been altered since it was issued. '
            'Do not trust this document.'
        )
    elif outcome == Outcome.UNVERIFIED:
        payload['warning'] = (
            'This certificate could not be checked against the blockchain right '
            'now. This does not mean it is invalid — please try again shortly.'
        )
        if chain_error:
            payload['detail'] = chain_error

    return payload


# ─── Endpoint (FR-5.1, NFR-1.4, NFR-1.7) ─────────────────────────────────────

@method_decorator(
    ratelimit(
        key=ratelimit_ip_key,
        rate=settings.RATELIMITS['public_verify'],  # 30/min, FR-5.8
        block=True,
    ),
    name='get',
)
class PublicVerifyView(APIView):
    """
    GET /api/public/verify/<certificate_id>/

    Unauthenticated and read-only. Only `get` is defined, so DRF answers any
    other method with 405 (NFR-1.4) — there is deliberately no code path here
    that can modify a certificate.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, certificate_id):
        result = verify_certificate(certificate_id)

        if result['status'] == Outcome.NOT_FOUND:
            return Response(
                {
                    'certificate_id': certificate_id,
                    'status': Outcome.NOT_FOUND,
                    'detail': 'No certificate was found with that ID.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result)
