"""
Input validation and sanitisation for certificate fields (FR-2.1.1, FR-2.1.2).

The values here end up in three places with different escaping rules: a
WeasyPrint HTML template, the canonical JSON that gets hashed and anchored
on-chain, and the public verification page. Rejecting dangerous input at the
edge is cheaper and safer than trying to escape correctly in all three.

Rejecting rather than stripping is deliberate. Silently stripping characters
would change the value *after* the issuer reviewed it, and since the certificate
hash is computed from the stored value, the issuer would be anchoring something
they never saw.
"""
from __future__ import annotations

import re
import unicodedata

from rest_framework import serializers

# Anything that could open an HTML tag or an entity. Certificate holders have
# names with apostrophes and hyphens, but never with angle brackets.
_HTML_LIKE = re.compile(r'[<>]|&[#a-zA-Z0-9]{2,8};')

# Defence in depth: catch the obvious payload shapes even without brackets.
_SCRIPTISH = re.compile(
    r'(javascript\s*:|data\s*:\s*text/html|vbscript\s*:|on\w+\s*=)',
    re.IGNORECASE,
)

# A leading =, +, - or @ makes spreadsheet software treat a cell as a formula.
# Certificate lists get exported to CSV, so this is a real path to code
# execution on the viewer's machine.
_FORMULA_PREFIX = re.compile(r'^[=+\-@\t\r]')

# C0/C1 control characters, excluding tab/newline which are handled separately.
_CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

# RFC 5322-shaped address check, applied on top of DRF's EmailField.
_EMAIL = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


def normalise_text(value: str) -> str:
    """
    NFC-normalise and collapse whitespace.

    Normalisation matters more than it looks: 'é' can be encoded as one code
    point or two, and the two forms produce different SHA-256 hashes. Without a
    fixed normal form, a certificate could be issued in one encoding and later
    fail verification purely because the text was re-typed in the other.
    """
    value = unicodedata.normalize('NFC', value)
    value = value.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    return re.sub(r'\s+', ' ', value).strip()


def validate_safe_text(value: str, field_label: str = 'This field') -> str:
    """Reject markup-like and control content, then normalise."""
    if _CONTROL.search(value):
        raise serializers.ValidationError(
            f'{field_label} contains control characters, which are not allowed.'
        )
    if _HTML_LIKE.search(value):
        raise serializers.ValidationError(
            f'{field_label} may not contain HTML markup or entities '
            '(characters such as < and >).'
        )
    if _SCRIPTISH.search(value):
        raise serializers.ValidationError(
            f'{field_label} contains script-like content, which is not allowed.'
        )

    cleaned = normalise_text(value)

    if not cleaned:
        raise serializers.ValidationError(f'{field_label} may not be blank.')
    if _FORMULA_PREFIX.match(cleaned):
        raise serializers.ValidationError(
            f'{field_label} may not begin with =, +, - or @.'
        )
    return cleaned


def validate_recipient_email(value: str) -> str:
    """RFC 5322 shape plus the 254-character RFC 5321 ceiling (FR-2.1.1)."""
    cleaned = value.strip().lower()

    if len(cleaned) > 254:
        raise serializers.ValidationError(
            'Email address may not exceed 254 characters.'
        )
    if not _EMAIL.match(cleaned):
        raise serializers.ValidationError('Enter a valid email address.')

    local_part = cleaned.rsplit('@', 1)[0]
    if len(local_part) > 64:
        raise serializers.ValidationError(
            'The part before @ may not exceed 64 characters.'
        )
    return cleaned
