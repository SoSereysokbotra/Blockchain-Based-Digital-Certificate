"""
Token issuance, rotation and revocation (SRS 3.1.2, FR-1.3, FR-1.5, FR-1.7, NFR-1.6).

Strategy:

  * Access token  — 15 minutes, returned in the JSON body, held in memory by the
    SPA. Short-lived because it is the one credential JavaScript can touch.
  * Refresh token — 7 days, delivered only as an httpOnly cookie so XSS cannot
    read it, and recorded server-side as a SHA-256 hash (NFR-1.6).
  * Rotation      — every refresh mints a new token and blacklists the old one.
    Presenting an already-rotated token is treated as theft: the whole session
    family is revoked rather than just the request being refused.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken

from .models import RefreshToken as RefreshTokenRecord


class InvalidRefreshToken(Exception):
    """Presented refresh token is missing, malformed, expired or revoked."""


def _expiry_from(token: JWTRefreshToken) -> datetime:
    return datetime.fromtimestamp(token['exp'], tz=dt_timezone.utc)


def issue_tokens(organization, *, ip=None, user_agent=''):
    """Mint an access/refresh pair and record the refresh token."""
    refresh = JWTRefreshToken.for_user(organization)

    RefreshTokenRecord.record(
        organization=organization,
        raw_token=str(refresh),
        jti=refresh['jti'],
        expires_at=_expiry_from(refresh),
        ip=ip,
        user_agent=user_agent,
    )

    return str(refresh.access_token), str(refresh)


def rotate_tokens(raw_refresh: str | None, *, ip=None, user_agent=''):
    """
    Validate a refresh token and swap it for a fresh pair (FR-1.5).

    Raises InvalidRefreshToken for anything that should produce a 401.
    """
    if not raw_refresh:
        raise InvalidRefreshToken('No refresh token supplied.')

    record = RefreshTokenRecord.lookup(raw_refresh)

    if record is not None and not record.is_active:
        # Reuse of a token we already rotated or revoked. The legitimate client
        # cannot do this, so assume the token leaked and drop every session for
        # the account rather than only rejecting this request.
        RefreshTokenRecord.revoke_all_for(record.organization)
        raise InvalidRefreshToken('Refresh token has already been used or revoked.')

    try:
        token = JWTRefreshToken(raw_refresh)
    except TokenError as exc:
        raise InvalidRefreshToken(str(exc)) from exc

    if record is None:
        # Signature is valid but we have no record — the row was purged, or the
        # token predates a reset. Refuse rather than silently trusting it.
        raise InvalidRefreshToken('Refresh token is not recognised.')

    organization = record.organization
    if not organization.is_active:
        raise InvalidRefreshToken('Account is inactive.')

    # Blacklist first: if anything below fails, the old token must already be
    # dead rather than left usable.
    try:
        token.blacklist()
    except AttributeError:  # pragma: no cover - blacklist app is installed
        pass
    record.revoke()

    access, new_refresh = issue_tokens(organization, ip=ip, user_agent=user_agent)
    return organization, access, new_refresh


def revoke_refresh_token(raw_refresh: str | None) -> None:
    """Best-effort revocation for logout (FR-1.7)."""
    if not raw_refresh:
        return

    record = RefreshTokenRecord.lookup(raw_refresh)
    if record is not None:
        record.revoke()

    try:
        JWTRefreshToken(raw_refresh).blacklist()
    except (TokenError, AttributeError):
        # Already expired or blacklisted — logout still succeeds.
        pass


def revoke_all_sessions(organization) -> int:
    """
    Kill every session for an organisation.

    Used after a password reset (Phase 3 completion criteria): whoever forced
    the reset must not keep a working session from before it.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    count = RefreshTokenRecord.revoke_all_for(organization)

    for outstanding in OutstandingToken.objects.filter(user=organization):
        BlacklistedToken.objects.get_or_create(token=outstanding)

    return count


# ─── Cookie helpers ──────────────────────────────────────────────────────────

def set_refresh_cookie(response, raw_refresh: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,                       # FR-1.3 — unreadable from JS
        secure=not settings.DEBUG,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path='/api/auth/',                   # only sent to the endpoints that need it
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path='/api/auth/',
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def read_refresh_cookie(request) -> str | None:
    return request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
