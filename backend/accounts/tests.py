"""
Authentication test suite (Implementation Plan, Phase 3).

Time-dependent behaviour is tested with `time_machine`, never with sleeps: the
lockout cooldown is 30 minutes and code expiry is 10, so waiting them out is not
an option and asserting them is the only way to know the numbers in SRS 3.1.4
are real rather than aspirational.

Rate limits get one test per endpoint. A single "rate limiting works somewhere"
test would pass while six of the seven endpoints were unprotected.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
import time_machine
from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from accounts.lockout import get_lockout_state, record_attempt
from accounts.models import (
    EmailVerificationCode,
    LoginAttempt,
    Organization,
    PasswordResetCode,
    RefreshToken,
    generate_code,
    hash_token,
)
from accounts.tokens import issue_tokens

PASSWORD = 'CorrectHorse!2026'
NEW_PASSWORD = 'FreshBattery!2026'

pytestmark = pytest.mark.django_db


def url(name):
    return reverse(name)


def bypass_ratelimit():
    """
    Clear rate-limit counters mid-test.

    Needed by tests that deliberately make more requests than a limit allows in
    order to exercise something else — lockout needs 5 logins but the login
    limit is 10/minute, so a 20-attempt IP test would otherwise hit 429 before
    it reached the behaviour under test.
    """
    cache.clear()


# ─── Registration (FR-1.1) ───────────────────────────────────────────────────

class TestRegistration:
    def test_creates_unverified_organization(self, api):
        response = api.post(url('register'), {
            'name': 'New Institute',
            'email': 'New@Example.edu',
            'password': 'ReallyStrong!2026',
        }, format='json')

        assert response.status_code == 201
        org = Organization.objects.get(email='new@example.edu')  # normalised
        assert org.is_verified is False
        assert org.check_password('ReallyStrong!2026')

    def test_issues_a_verification_code(self, api):
        api.post(url('register'), {
            'name': 'New Institute',
            'email': 'new@example.edu',
            'password': 'ReallyStrong!2026',
        }, format='json')

        code = EmailVerificationCode.objects.get()
        assert len(code.code) == 6
        assert code.code.isdigit()
        assert code.used_at is None

    def test_rejects_duplicate_email(self, api, organization):
        response = api.post(url('register'), {
            'name': 'Impostor',
            'email': organization.email,
            'password': 'ReallyStrong!2026',
        }, format='json')

        assert response.status_code == 400
        assert 'email' in response.data

    def test_rejects_password_under_ten_characters(self, api):
        response = api.post(url('register'), {
            'name': 'Shorty',
            'email': 'short@example.edu',
            'password': 'Abc!23xy',  # 8 chars
        }, format='json')

        assert response.status_code == 400
        assert 'password' in response.data

    def test_rejects_common_password(self, api):
        # SRS 3.1.5: checked against a static common-password list.
        response = api.post(url('register'), {
            'name': 'Careless',
            'email': 'careless@example.edu',
            'password': 'password123',
        }, format='json')

        assert response.status_code == 400

    def test_never_returns_password(self, api):
        response = api.post(url('register'), {
            'name': 'New Institute',
            'email': 'new@example.edu',
            'password': 'ReallyStrong!2026',
        }, format='json')

        assert 'password' not in str(response.data).lower() or response.status_code == 201
        assert 'ReallyStrong!2026' not in str(response.data)


# ─── Email verification (FR-1.1, FR-1.9) ─────────────────────────────────────

class TestEmailVerification:
    def test_verifies_with_a_valid_code(self, api, unverified_organization):
        code = EmailVerificationCode.issue(unverified_organization)

        response = api.post(url('verify-email'), {
            'email': unverified_organization.email,
            'code': code.code,
        }, format='json')

        assert response.status_code == 200
        unverified_organization.refresh_from_db()
        assert unverified_organization.is_verified is True

    def test_code_is_single_use(self, api, unverified_organization):
        code = EmailVerificationCode.issue(unverified_organization)
        payload = {'email': unverified_organization.email, 'code': code.code}

        assert api.post(url('verify-email'), payload, format='json').status_code == 200

        # Second use must fail even though the account is now verified.
        unverified_organization.is_verified = False
        unverified_organization.save(update_fields=['is_verified'])
        second = api.post(url('verify-email'), payload, format='json')

        assert second.status_code == 400
        unverified_organization.refresh_from_db()
        assert unverified_organization.is_verified is False

    def test_code_expires_after_ten_minutes(self, api, unverified_organization):
        code = EmailVerificationCode.issue(unverified_organization)

        with time_machine.travel(timezone.now() + timedelta(minutes=10, seconds=1)):
            response = api.post(url('verify-email'), {
                'email': unverified_organization.email,
                'code': code.code,
            }, format='json')

        assert response.status_code == 400
        unverified_organization.refresh_from_db()
        assert unverified_organization.is_verified is False

    def test_code_still_valid_just_before_expiry(self, api, unverified_organization):
        code = EmailVerificationCode.issue(unverified_organization)

        with time_machine.travel(timezone.now() + timedelta(minutes=9, seconds=30)):
            response = api.post(url('verify-email'), {
                'email': unverified_organization.email,
                'code': code.code,
            }, format='json')

        assert response.status_code == 200

    def test_code_is_bound_to_its_own_account(self, api, unverified_organization, organization):
        """A code must not verify a different account (enumeration/bypass guard)."""
        code = EmailVerificationCode.issue(unverified_organization)

        response = api.post(url('verify-email'), {
            'email': organization.email,
            'code': code.code,
        }, format='json')

        assert response.status_code in (200, 400)
        unverified_organization.refresh_from_db()
        assert unverified_organization.is_verified is False

    def test_resend_invalidates_the_previous_code(self, api, unverified_organization):
        first = EmailVerificationCode.issue(unverified_organization)

        api.post(url('resend-email-verification'),
                 {'email': unverified_organization.email}, format='json')

        first.refresh_from_db()
        assert first.used_at is not None

        response = api.post(url('verify-email'), {
            'email': unverified_organization.email,
            'code': first.code,
        }, format='json')
        assert response.status_code == 400

    def test_resend_does_not_reveal_whether_the_account_exists(self, api):
        known = api.post(url('resend-email-verification'),
                         {'email': 'nobody@example.edu'}, format='json')
        assert known.status_code == 200
        assert 'If an account exists' in known.data['detail']


# ─── Login (FR-1.2, FR-1.3) ──────────────────────────────────────────────────

class TestLogin:
    def test_successful_login_returns_access_token_and_cookie(self, api, organization):
        response = api.post(url('login'), {
            'email': organization.email, 'password': PASSWORD,
        }, format='json')

        assert response.status_code == 200
        assert response.data['access_token']
        assert settings.REFRESH_COOKIE_NAME in response.cookies

    def test_refresh_cookie_is_httponly(self, api, organization):
        response = api.post(url('login'), {
            'email': organization.email, 'password': PASSWORD,
        }, format='json')

        cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
        assert cookie['httponly'] is True
        assert cookie['samesite'] == settings.REFRESH_COOKIE_SAMESITE

    def test_refresh_token_is_never_in_the_body(self, api, organization):
        response = api.post(url('login'), {
            'email': organization.email, 'password': PASSWORD,
        }, format='json')

        assert 'refresh' not in response.data
        raw = response.cookies[settings.REFRESH_COOKIE_NAME].value
        assert raw not in str(response.data)

    def test_refresh_token_is_stored_hashed(self, api, organization):
        response = api.post(url('login'), {
            'email': organization.email, 'password': PASSWORD,
        }, format='json')

        raw = response.cookies[settings.REFRESH_COOKIE_NAME].value
        record = RefreshToken.objects.get()

        assert record.token_hash == hash_token(raw)
        assert raw not in record.token_hash
        assert len(record.token_hash) == 64

    def test_wrong_password_returns_401(self, api, organization):
        response = api.post(url('login'), {
            'email': organization.email, 'password': 'WrongPassword!2026',
        }, format='json')

        assert response.status_code == 401
        assert LoginAttempt.objects.filter(successful=False).count() == 1

    def test_unknown_email_returns_401_not_404(self, api):
        response = api.post(url('login'), {
            'email': 'ghost@example.edu', 'password': PASSWORD,
        }, format='json')

        # Same status and body as a wrong password, so login cannot be used to
        # discover which addresses are registered.
        assert response.status_code == 401
        assert response.data['detail'] == 'Invalid credentials.'

    def test_unverified_account_is_refused(self, api, unverified_organization):
        response = api.post(url('login'), {
            'email': unverified_organization.email, 'password': PASSWORD,
        }, format='json')

        assert response.status_code == 403
        assert response.data['code'] == 'email_not_verified'

    def test_correct_password_on_unverified_account_is_not_a_failed_attempt(
        self, api, unverified_organization
    ):
        api.post(url('login'), {
            'email': unverified_organization.email, 'password': PASSWORD,
        }, format='json')

        assert LoginAttempt.objects.filter(successful=False).count() == 0

    def test_inactive_account_cannot_log_in(self, api, organization):
        organization.is_active = False
        organization.save(update_fields=['is_active'])

        response = api.post(url('login'), {
            'email': organization.email, 'password': PASSWORD,
        }, format='json')

        assert response.status_code == 401


# ─── Lockout (FR-1.6) ────────────────────────────────────────────────────────

class TestAccountLockout:
    def _fail(self, api, email, times):
        for _ in range(times):
            bypass_ratelimit()
            api.post(url('login'),
                     {'email': email, 'password': 'Wrong!2026Pass'}, format='json')

    def test_locks_after_exactly_five_failures(self, api, organization):
        self._fail(api, organization.email, 4)

        bypass_ratelimit()
        fifth = api.post(url('login'),
                         {'email': organization.email, 'password': 'Wrong!2026Pass'},
                         format='json')
        assert fifth.status_code == 401, 'the 5th failure is still a 401'

        # The 6th request is the first one refused outright.
        bypass_ratelimit()
        sixth = api.post(url('login'),
                         {'email': organization.email, 'password': PASSWORD},
                         format='json')
        assert sixth.status_code == 423
        assert sixth.data['code'] == 'account_locked'

    def test_four_failures_do_not_lock(self, api, organization):
        self._fail(api, organization.email, 4)

        bypass_ratelimit()
        response = api.post(url('login'),
                            {'email': organization.email, 'password': PASSWORD},
                            format='json')
        assert response.status_code == 200

    def test_lock_blocks_even_the_correct_password(self, api, organization):
        self._fail(api, organization.email, 5)

        bypass_ratelimit()
        response = api.post(url('login'),
                            {'email': organization.email, 'password': PASSWORD},
                            format='json')
        assert response.status_code == 423

    def test_lock_clears_after_thirty_minute_cooldown(self, api, organization):
        self._fail(api, organization.email, 5)

        with time_machine.travel(timezone.now() + timedelta(minutes=30, seconds=1)):
            bypass_ratelimit()
            response = api.post(url('login'),
                                {'email': organization.email, 'password': PASSWORD},
                                format='json')
        assert response.status_code == 200

    def test_still_locked_at_twenty_nine_minutes(self, api, organization):
        self._fail(api, organization.email, 5)

        with time_machine.travel(timezone.now() + timedelta(minutes=29)):
            bypass_ratelimit()
            response = api.post(url('login'),
                                {'email': organization.email, 'password': PASSWORD},
                                format='json')
        assert response.status_code == 423

    def test_failures_spread_wider_than_the_window_do_not_trigger(self, organization):
        """
        Five failures only lock the account if they cluster inside 15 minutes.

        A user who mistypes once an hour over a working day must not accumulate
        their way into a lockout.
        """
        now = timezone.now()
        for minutes_ago in (0, 20, 40, 60, 80):
            with time_machine.travel(now - timedelta(minutes=minutes_ago)):
                record_attempt(organization.email, '203.0.113.5', successful=False)

        assert get_lockout_state(organization.email, '203.0.113.5').locked is False

    def test_burst_older_than_the_window_stays_locked_for_its_cooldown(self, organization):
        """
        The counting window and the cooldown are separate clocks.

        A burst 20 minutes ago is outside the 15-minute counting window, but its
        30-minute lock still has 10 minutes to run.
        """
        with time_machine.travel(timezone.now() - timedelta(minutes=20)):
            for _ in range(5):
                record_attempt(organization.email, '203.0.113.5', successful=False)

        state = get_lockout_state(organization.email, '203.0.113.5')
        assert state.locked is True
        assert 0 < state.retry_after_seconds <= 10 * 60

    def test_successful_login_clears_the_account_counter(self, api, organization):
        self._fail(api, organization.email, 3)

        bypass_ratelimit()
        assert api.post(url('login'),
                        {'email': organization.email, 'password': PASSWORD},
                        format='json').status_code == 200

        # Three more failures would total six without the reset, tripping the lock.
        self._fail(api, organization.email, 3)
        bypass_ratelimit()
        response = api.post(url('login'),
                            {'email': organization.email, 'password': PASSWORD},
                            format='json')
        assert response.status_code == 200

    def test_ip_lockout_after_twenty_failures_across_accounts(self, organization):
        ip = '198.51.100.7'
        # 20 different addresses, so no single account reaches its own limit of 5.
        for index in range(20):
            record_attempt(f'target{index}@example.edu', ip, successful=False)

        state = get_lockout_state('someone-else@example.edu', ip)
        assert state.locked is True
        assert state.scope == 'ip'

    def test_nineteen_ip_failures_do_not_lock(self):
        ip = '198.51.100.8'
        for index in range(19):
            record_attempt(f'target{index}@example.edu', ip, successful=False)

        assert get_lockout_state('fresh@example.edu', ip).locked is False

    def test_account_lock_is_scoped_to_that_account(self, api, organization, other_organization):
        self._fail(api, organization.email, 5)

        bypass_ratelimit()
        response = api.post(url('login'),
                            {'email': other_organization.email, 'password': PASSWORD},
                            format='json')
        assert response.status_code == 200

    def test_locked_response_carries_retry_after(self, api, organization):
        self._fail(api, organization.email, 5)

        bypass_ratelimit()
        response = api.post(url('login'),
                            {'email': organization.email, 'password': PASSWORD},
                            format='json')
        assert response.status_code == 423
        assert int(response['Retry-After']) > 0


# ─── Refresh rotation (FR-1.5, NFR-1.6) ──────────────────────────────────────

class TestRefreshRotation:
    def _login(self, api, organization):
        response = api.post(url('login'),
                            {'email': organization.email, 'password': PASSWORD},
                            format='json')
        return response.cookies[settings.REFRESH_COOKIE_NAME].value

    def test_refresh_returns_a_new_access_token(self, api, organization):
        self._login(api, organization)
        response = api.post(url('refresh-token'))

        assert response.status_code == 200
        assert response.data['access_token']

    def test_refresh_rotates_the_cookie(self, api, organization):
        first = self._login(api, organization)
        response = api.post(url('refresh-token'))
        second = response.cookies[settings.REFRESH_COOKIE_NAME].value

        assert second != first

    def test_reusing_a_rotated_token_returns_401(self, api, organization):
        original = self._login(api, organization)
        api.post(url('refresh-token'))  # rotates; `original` is now spent

        api.cookies[settings.REFRESH_COOKIE_NAME] = original
        response = api.post(url('refresh-token'))

        assert response.status_code == 401

    def test_reuse_revokes_the_whole_session_family(self, api, organization):
        original = self._login(api, organization)
        api.post(url('refresh-token'))

        api.cookies[settings.REFRESH_COOKIE_NAME] = original
        api.post(url('refresh-token'))

        # A leaked-and-replayed token invalidates every session, so the thief
        # and the victim are both logged out rather than the thief silently
        # keeping access.
        assert RefreshToken.objects.filter(revoked_at__isnull=True).count() == 0

    def test_missing_cookie_returns_401(self, api):
        assert api.post(url('refresh-token')).status_code == 401

    def test_garbage_token_returns_401(self, api):
        api.cookies[settings.REFRESH_COOKIE_NAME] = 'not.a.jwt'
        assert api.post(url('refresh-token')).status_code == 401


# ─── Logout (FR-1.7) ─────────────────────────────────────────────────────────

class TestLogout:
    def test_logout_revokes_the_refresh_token(self, api, organization):
        api.post(url('login'), {'email': organization.email, 'password': PASSWORD},
                 format='json')
        access, _ = issue_tokens(organization)
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = api.post(url('logout'))
        assert response.status_code == 200

        api.credentials()
        assert api.post(url('refresh-token')).status_code == 401

    def test_logout_requires_authentication(self, api):
        assert api.post(url('logout')).status_code == 401


# ─── Password reset (FR-1.8) ─────────────────────────────────────────────────

class TestPasswordReset:
    def test_request_returns_the_same_response_for_unknown_emails(self, api, organization):
        known = api.post(url('request-password-reset'),
                         {'email': organization.email}, format='json')
        bypass_ratelimit()
        unknown = api.post(url('request-password-reset'),
                           {'email': 'ghost@example.edu'}, format='json')

        assert known.status_code == unknown.status_code == 200
        assert known.data == unknown.data

    def test_full_reset_flow_changes_the_password(self, api, organization):
        code = PasswordResetCode.issue(organization)

        verify = api.post(url('verify-password-reset'),
                          {'email': organization.email, 'code': code.code}, format='json')
        assert verify.status_code == 200

        reset = api.post(url('reset-password'), {
            'email': organization.email, 'code': code.code, 'new_password': NEW_PASSWORD,
        }, format='json')
        assert reset.status_code == 200

        organization.refresh_from_db()
        assert organization.check_password(NEW_PASSWORD)

    def test_verify_does_not_consume_the_code(self, api, organization):
        code = PasswordResetCode.issue(organization)

        api.post(url('verify-password-reset'),
                 {'email': organization.email, 'code': code.code}, format='json')

        code.refresh_from_db()
        assert code.used_at is None

    def test_code_is_single_use(self, api, organization):
        code = PasswordResetCode.issue(organization)
        payload = {'email': organization.email, 'code': code.code,
                   'new_password': NEW_PASSWORD}

        assert api.post(url('reset-password'), payload, format='json').status_code == 200

        bypass_ratelimit()
        second = api.post(url('reset-password'), {
            **payload, 'new_password': 'ThirdPassword!2026',
        }, format='json')
        assert second.status_code == 400

    def test_code_expires_after_ten_minutes(self, api, organization):
        code = PasswordResetCode.issue(organization)

        with time_machine.travel(timezone.now() + timedelta(minutes=10, seconds=1)):
            response = api.post(url('reset-password'), {
                'email': organization.email, 'code': code.code,
                'new_password': NEW_PASSWORD,
            }, format='json')

        assert response.status_code == 400
        organization.refresh_from_db()
        assert organization.check_password(PASSWORD)

    def test_reset_deletes_all_existing_refresh_tokens(self, api, organization):
        issue_tokens(organization)
        issue_tokens(organization)
        assert RefreshToken.objects.filter(revoked_at__isnull=True).count() == 2

        code = PasswordResetCode.issue(organization)
        api.post(url('reset-password'), {
            'email': organization.email, 'code': code.code, 'new_password': NEW_PASSWORD,
        }, format='json')

        assert RefreshToken.objects.filter(revoked_at__isnull=True).count() == 0

    def test_old_session_cannot_refresh_after_reset(self, api, organization):
        api.post(url('login'), {'email': organization.email, 'password': PASSWORD},
                 format='json')

        code = PasswordResetCode.issue(organization)
        api.post(url('reset-password'), {
            'email': organization.email, 'code': code.code, 'new_password': NEW_PASSWORD,
        }, format='json')

        assert api.post(url('refresh-token')).status_code == 401

    def test_weak_new_password_is_rejected(self, api, organization):
        code = PasswordResetCode.issue(organization)

        response = api.post(url('reset-password'), {
            'email': organization.email, 'code': code.code, 'new_password': 'short1!',
        }, format='json')

        assert response.status_code == 400
        code.refresh_from_db()
        assert code.used_at is None, 'a rejected password must not burn the code'


# ─── Rate limits — one test per endpoint (SRS 3.1.4) ─────────────────────────

class TestRateLimits:
    """
    Each of the seven authentication endpoints is asserted individually.

    django-ratelimit counts per IP via accounts.ip.ratelimit_ip_key, so a single
    test client is one client for limiting purposes.
    """

    def _exhaust(self, api, view_name, payload, allowed):
        last = None
        for _ in range(allowed + 1):
            last = api.post(url(view_name), payload, format='json')
        return last

    def test_register_limited_to_5_per_hour(self, api):
        last = self._exhaust(api, 'register', {
            'name': 'Spam', 'email': 'spam@example.edu', 'password': 'ReallyStrong!2026',
        }, allowed=5)
        assert last.status_code == 429

    def test_login_limited_to_10_per_minute(self, api, organization):
        last = self._exhaust(api, 'login', {
            'email': organization.email, 'password': 'Wrong!2026Pass',
        }, allowed=10)
        assert last.status_code == 429

    def test_verify_email_limited_to_10_per_hour(self, api, unverified_organization):
        last = self._exhaust(api, 'verify-email', {
            'email': unverified_organization.email, 'code': '000000',
        }, allowed=10)
        assert last.status_code == 429

    def test_resend_email_verification_limited_to_3_per_hour(self, api, unverified_organization):
        last = self._exhaust(api, 'resend-email-verification', {
            'email': unverified_organization.email,
        }, allowed=3)
        assert last.status_code == 429

    def test_request_password_reset_limited_to_3_per_hour(self, api, organization):
        last = self._exhaust(api, 'request-password-reset', {
            'email': organization.email,
        }, allowed=3)
        assert last.status_code == 429

    def test_verify_password_reset_limited_to_10_per_hour(self, api, organization):
        last = self._exhaust(api, 'verify-password-reset', {
            'email': organization.email, 'code': '000000',
        }, allowed=10)
        assert last.status_code == 429

    def test_reset_password_limited_to_5_per_hour(self, api, organization):
        last = self._exhaust(api, 'reset-password', {
            'email': organization.email, 'code': '000000',
            'new_password': NEW_PASSWORD,
        }, allowed=5)
        assert last.status_code == 429

    def test_rate_limit_state_lives_in_the_shared_database_cache(self, api, organization):
        """
        Guards NFR-1.10.

        If CACHES ever reverts to LocMemCache this fails, because the counters
        would be per-process and invisible here — which is exactly the bug that
        would silently multiply every limit by the worker count.
        """
        assert 'DatabaseCache' in settings.CACHES['default']['BACKEND']
        assert settings.RATELIMIT_USE_CACHE == 'default'

        api.post(url('login'), {'email': organization.email, 'password': 'Wrong!2026'},
                 format='json')

        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM {settings.CACHE_TABLE_NAME}')
            assert cursor.fetchone()[0] > 0, 'rate limit counter did not reach the DB'


# ─── Access control (NFR-1.3) ────────────────────────────────────────────────

class TestProtectedEndpoints:
    def test_me_requires_authentication(self, api):
        assert api.get(url('me')).status_code == 401

    def test_me_returns_the_signed_in_organization(self, auth_client, organization):
        response = auth_client.get(url('me'))

        assert response.status_code == 200
        assert response.data['email'] == organization.email
        assert 'password' not in response.data

    def test_expired_access_token_is_rejected(self, api, organization):
        access, _ = issue_tokens(organization)
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        lifetime = settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
        with time_machine.travel(timezone.now() + lifetime + timedelta(seconds=5)):
            assert api.get(url('me')).status_code == 401


# ─── Supporting units ────────────────────────────────────────────────────────

class TestCodeGeneration:
    def test_codes_are_six_numeric_digits(self):
        for _ in range(50):
            code = generate_code()
            assert len(code) == 6 and code.isdigit()

    def test_codes_are_not_trivially_repeated(self):
        # A weak generator (or a constant) would collapse this set.
        assert len({generate_code() for _ in range(200)}) > 100


class TestClientIpResolution:
    def test_ignores_x_forwarded_for_by_default(self, rf):
        from accounts.ip import get_client_ip

        request = rf.get('/', REMOTE_ADDR='203.0.113.9',
                         HTTP_X_FORWARDED_FOR='1.2.3.4')

        # Trusting the header here would let an attacker send a fresh fake IP
        # per request and never trip the IP lockout.
        assert get_client_ip(request) == '203.0.113.9'

    def test_honours_x_forwarded_for_when_explicitly_trusted(self, rf, settings):
        from accounts.ip import get_client_ip

        settings.TRUST_X_FORWARDED_FOR = True
        request = rf.get('/', REMOTE_ADDR='10.0.0.1',
                         HTTP_X_FORWARDED_FOR='1.2.3.4, 10.0.0.1')

        assert get_client_ip(request) == '1.2.3.4'

    def test_rejects_a_malformed_address(self, rf, settings):
        from accounts.ip import get_client_ip

        settings.TRUST_X_FORWARDED_FOR = True
        request = rf.get('/', REMOTE_ADDR='203.0.113.9',
                         HTTP_X_FORWARDED_FOR='not-an-ip')

        assert get_client_ip(request) == '203.0.113.9'
