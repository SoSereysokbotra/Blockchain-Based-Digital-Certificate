"""
Account and IP lockout, computed from the LoginAttempt log (FR-1.6).

Thresholds (SRS 3.1.4 / Implementation Plan Phase 3):

    5  failed attempts for one account   within a 15-minute window
    20 failed attempts from one IP       within a 15-minute window
    30-minute cooldown once locked

The cooldown is measured from the most recent failure, not from the moment the
lock engaged: continuing to guess while locked out extends the lock rather than
letting the clock run down under attack.

Everything is derived by querying LoginAttempt rather than by keeping counters.
That costs one indexed query per login, and buys three things a counter column
cannot give: the IP rule can aggregate across accounts that do not exist (an
attacker spraying random emails), the window slides correctly with no cleanup
job on the critical path, and the audit trail and the enforcement can never
disagree because they are the same rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LoginAttempt


@dataclass(frozen=True)
class LockoutState:
    locked: bool
    scope: str | None          # 'account' | 'ip' | None
    retry_after_seconds: int   # 0 when not locked

    @property
    def message(self) -> str:
        if not self.locked:
            return ''
        minutes = max(1, round(self.retry_after_seconds / 60))
        if self.scope == 'ip':
            return (
                'Too many failed sign-in attempts from this network. '
                f'Try again in about {minutes} minute(s).'
            )
        return (
            'This account is temporarily locked after too many failed sign-in '
            f'attempts. Try again in about {minutes} minute(s).'
        )


def _window_start():
    return timezone.now() - timedelta(minutes=settings.LOCKOUT_WINDOW_MINUTES)


def _evaluate(queryset, threshold: int, scope: str) -> LockoutState | None:
    """
    Return a locked state if `threshold` failures fell inside the window.

    Two distinct clocks, which are easy to conflate:

      * WINDOW (15 min) decides whether a lock *triggers* — the failures must
        be clustered this closely to count as an attack rather than a user
        mistyping their password over the course of a morning.
      * COOLDOWN (30 min) decides how long the lock *lasts*, measured from the
        most recent failure.

    So the lookback has to span the cooldown, not the window: a burst 20 minutes
    ago is outside the counting window but its 30-minute lock is still running,
    and querying only the last 15 minutes would let the lock silently expire
    early.
    """
    now = timezone.now()
    window = timedelta(minutes=settings.LOCKOUT_WINDOW_MINUTES)
    cooldown = timedelta(minutes=settings.LOCKOUT_COOLDOWN_MINUTES)

    recent = list(
        queryset.filter(successful=False, attempted_at__gte=now - max(window, cooldown))
        .order_by('-attempted_at')
        .values_list('attempted_at', flat=True)[:threshold]
    )

    if len(recent) < threshold:
        return None

    newest, oldest = recent[0], recent[-1]
    if newest - oldest > window:
        # Enough failures exist, but spread too thinly to have tripped the rule.
        return None

    remaining = ((newest + cooldown) - now).total_seconds()
    if remaining <= 0:
        return None

    return LockoutState(locked=True, scope=scope, retry_after_seconds=int(remaining))


def get_lockout_state(email: str, ip: str | None) -> LockoutState:
    """Check the account rule first, then the IP rule."""
    account_state = _evaluate(
        LoginAttempt.objects.filter(email=email.lower()),
        settings.ACCOUNT_LOCKOUT_THRESHOLD,
        'account',
    )
    if account_state:
        return account_state

    if ip:
        ip_state = _evaluate(
            LoginAttempt.objects.filter(ip_address=ip),
            settings.IP_LOCKOUT_THRESHOLD,
            'ip',
        )
        if ip_state:
            return ip_state

    return LockoutState(locked=False, scope=None, retry_after_seconds=0)


def record_attempt(email: str, ip: str | None, *, successful: bool, user_agent: str = ''):
    return LoginAttempt.objects.create(
        email=(email or '').lower(),
        ip_address=ip,
        successful=successful,
        user_agent=(user_agent or '')[:300],
    )


def clear_account_failures(email: str) -> int:
    """
    Drop an account's failed attempts after a successful sign-in.

    Without this, a user who fails four times and then succeeds would still be
    one failure away from a lockout for the rest of the window.

    Only the *account* rule is cleared. IP failures survive, because a
    successful login for one account says nothing about an attacker spraying
    others from the same address.
    """
    return LoginAttempt.objects.filter(
        email=(email or '').lower(),
        successful=False,
        attempted_at__gte=_window_start(),
    ).delete()[0]


def purge_old_attempts(days: int = 30) -> int:
    """Housekeeping for the scheduled cleanup task."""
    cutoff = timezone.now() - timedelta(days=days)
    return LoginAttempt.objects.filter(attempted_at__lt=cutoff).delete()[0]
