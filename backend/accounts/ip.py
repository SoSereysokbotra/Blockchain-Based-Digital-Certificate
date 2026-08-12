"""
Client IP resolution — the single source of truth (NFR-1.11).

Every place that needs a client IP (login lockout, rate limiting, refresh-token
records, public verification throttling) calls `get_client_ip` here. Having one
implementation is the point: two subtly different ones would let an attacker
locked out under one rule stay unthrottled under another.

THE DECISION, stated explicitly:

    This deployment runs with no reverse proxy in front of Django, so
    REMOTE_ADDR is the true peer address and X-Forwarded-For is entirely
    attacker-supplied. It is therefore IGNORED by default.

    Honouring an untrusted X-Forwarded-For would completely defeat IP-based
    lockout (FR-1.6) and rate limiting (SRS 3.1.4): an attacker would simply
    send a different fake header on every request and never hit a limit.

    If BCIP is later deployed behind a proxy that *overwrites* (not appends to)
    X-Forwarded-For, set TRUST_X_FORWARDED_FOR=1. Only then is the left-most
    entry read, and only because the trusted proxy guarantees it. Turning that
    flag on without such a proxy reintroduces the bypass above.
"""
from __future__ import annotations

import ipaddress

from django.conf import settings


def get_client_ip(request) -> str | None:
    """Resolve the client IP under the documented policy. None if unresolvable."""
    if getattr(settings, 'TRUST_X_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            # Left-most is the original client when a trusted proxy sets it.
            candidate = forwarded.split(',')[0].strip()
            if _is_valid_ip(candidate):
                return candidate

    remote = (request.META.get('REMOTE_ADDR') or '').strip()
    return remote if _is_valid_ip(remote) else None


def _is_valid_ip(value: str) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def ratelimit_ip_key(group, request) -> str:
    """
    Key function for django-ratelimit, so it throttles on the same IP this
    module resolves rather than on its own built-in `ip` key (which reads
    REMOTE_ADDR directly and would diverge from the policy above once
    TRUST_X_FORWARDED_FOR is enabled).
    """
    return get_client_ip(request) or 'unknown'
