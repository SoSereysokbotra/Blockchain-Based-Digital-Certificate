"""
Canonical certificate hashing (SRS 7.2.1) — THE SINGLE DEFINITION SITE.

Both issuance and verification import `compute_certificate_hash` from here. If a
second implementation ever appears, the two will drift and every certificate
issued under one will report TAMPERED under the other. Phase 9 has an automated
check that this function is defined exactly once.

The canonical form is frozen and versioned. Changing any of the following is a
BREAKING change that invalidates every certificate already anchored on-chain,
and therefore requires bumping CANONICAL_VERSION and keeping the old branch
alive for existing records:

  * the set of fields included
  * their key names
  * how each value is rendered as a string
  * JSON separators, key ordering and encoding

Specific decisions, each of which is a way this could silently break:

  * ``sort_keys=True`` — Python dict order is insertion order, so without this
    a refactor that reorders the literal would change every hash.
  * ``separators=(',', ':')`` — the default ``json.dumps`` inserts a space
    after ':' and ',', so a stray default would change every hash.
  * Dates as ``YYYY-MM-DD`` via ``.isoformat()`` — never ``str(datetime)``,
    which would embed a time component and a timezone.
  * ``expiry_date`` absent is ``None``, never ``''`` — those are different
    JSON values and hash differently.
  * Text is NFC-normalised and whitespace-collapsed at input (validators.py),
    so 'é' has one representation by the time it reaches this function.
  * ``ensure_ascii=False`` with an explicit UTF-8 encode — the alternative
    escapes non-ASCII into ``\\uXXXX``, which is stable but makes the payload
    unreadable when debugging a mismatch.
"""
from __future__ import annotations

import hashlib
import json

CANONICAL_VERSION = 1


def canonical_payload(certificate) -> dict:
    """The exact field set that gets hashed. Field names are part of the spec."""
    return {
        'v': CANONICAL_VERSION,
        'certId': certificate.certificate_id,
        'orgId': str(certificate.organization_id),
        'recipientName': certificate.recipient_name,
        'recipientEmail': certificate.recipient_email,
        'courseTitle': certificate.course_title,
        'issueDate': certificate.issue_date.isoformat(),
        'expiryDate': (
            certificate.expiry_date.isoformat() if certificate.expiry_date else None
        ),
    }


def canonical_bytes(certificate) -> bytes:
    """Deterministic byte serialisation of the payload."""
    return json.dumps(
        canonical_payload(certificate),
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')


def compute_certificate_hash(certificate) -> str:
    """
    SHA-256 of the canonical bytes, as '0x' + 64 lowercase hex characters.

    The 0x prefix is carried so the stored value reads unambiguously as a
    32-byte hex quantity; it is stripped before the value is passed to the
    contract as bytes32.
    """
    return '0x' + hashlib.sha256(canonical_bytes(certificate)).hexdigest()


def hashes_match(left: str | None, right: str | None) -> bool:
    """
    Compare two hashes tolerantly of case and 0x prefix.

    The chain returns lowercase without a prefix and the database stores it
    with one, so a naive `==` would report TAMPERED for every valid
    certificate.
    """
    if not left or not right:
        return False
    return (
        left.removeprefix('0x').lower() == right.removeprefix('0x').lower()
    )
