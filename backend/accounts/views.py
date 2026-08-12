"""
Authentication endpoints (FR-1.1 – FR-1.9).

Two conventions run through every view here:

  * Rate limits come from settings.RATELIMITS and are keyed by the NFR-1.11 IP
    policy, so all seven endpoints throttle on the same notion of "client".
  * Endpoints that take an email address always return the same response
    whether or not that account exists. Anything else turns the auth surface
    into an account-enumeration oracle.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .ip import get_client_ip, ratelimit_ip_key
from .lockout import clear_account_failures, get_lockout_state, record_attempt
from .models import EmailVerificationCode, Organization, PasswordResetCode
from .serializers import (
    EmailOnlySerializer,
    LoginSerializer,
    OrganizationSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
    VerifyPasswordResetSerializer,
)
from .tokens import (
    InvalidRefreshToken,
    clear_refresh_cookie,
    issue_tokens,
    read_refresh_cookie,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_tokens,
    set_refresh_cookie,
)

logger = logging.getLogger(__name__)

# Identical wording for "sent" and "no such account" (see module docstring).
GENERIC_CODE_SENT = {
    'detail': 'If an account exists for that email, a code has been sent.'
}


def limit(name: str):
    """Apply the SRS 3.1.4 limit registered under `name` to a view class."""
    return method_decorator(
        ratelimit(key=ratelimit_ip_key, rate=settings.RATELIMITS[name], block=True),
        name='post',
    )


def _request_context(request):
    return {
        'ip': get_client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
    }


def _send_async(task_path: str, *args) -> None:
    """
    Queue an email. Falls back to running inline if the cluster is unreachable
    so that a stopped worker degrades delivery latency rather than breaking
    registration outright.
    """
    try:
        from django_q.tasks import async_task

        async_task(task_path, *args)
    except Exception:  # noqa: BLE001
        logger.warning('Queue unavailable; sending %s inline.', task_path, exc_info=True)
        module_path, _, func_name = task_path.rpartition('.')
        module = __import__(module_path, fromlist=[func_name])
        getattr(module, func_name)(*args)


# ─── Registration and email verification ─────────────────────────────────────

@limit('register')
class RegisterView(APIView):
    """FR-1.1 — create an unverified organisation and email a code."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            organization = serializer.save()
            code = EmailVerificationCode.issue(organization)

        _send_async('accounts.tasks.send_verification_email', str(organization.id), code.code)

        return Response(
            {'detail': 'Registration successful. Check your email for a '
                       'verification code, valid for 10 minutes.'},
            status=status.HTTP_201_CREATED,
        )


@limit('verify_email')
class VerifyEmailView(APIView):
    """FR-1.1 — consume a verification code."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']

        organization = Organization.objects.filter(email=email).first()
        if organization is None:
            return Response(
                {'detail': 'Invalid or expired verification code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if organization.is_verified:
            return Response({'detail': 'Email is already verified.'})

        record = (
            EmailVerificationCode.objects
            .filter(organization=organization, code=code)
            .order_by('-created_at')
            .first()
        )

        if record is None or not record.is_usable:
            return Response(
                {'detail': 'Invalid or expired verification code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            record.consume()
            organization.is_verified = True
            organization.save(update_fields=['is_verified', 'updated_at'])

        return Response({'detail': 'Email verified. You can now sign in.'})


@limit('resend_verification')
class ResendEmailVerificationView(APIView):
    """FR-1.9 — reissue a verification code."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = Organization.objects.filter(
            email=serializer.validated_data['email']
        ).first()

        if organization is not None and not organization.is_verified:
            code = EmailVerificationCode.issue(organization)
            _send_async(
                'accounts.tasks.send_verification_email', str(organization.id), code.code
            )

        return Response(GENERIC_CODE_SENT)


# ─── Session lifecycle ───────────────────────────────────────────────────────

@limit('login')
class LoginView(APIView):
    """FR-1.2, FR-1.3, FR-1.6 — authenticate and open a session."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        ctx = _request_context(request)

        # Lockout is checked before the password so a locked account cannot be
        # used as an oracle for whether a guess was correct.
        state = get_lockout_state(email, ctx['ip'])
        if state.locked:
            response = Response(
                {'detail': state.message, 'code': 'account_locked'},
                status=status.HTTP_423_LOCKED,
            )
            response['Retry-After'] = str(state.retry_after_seconds)
            return response

        organization = Organization.objects.filter(email=email).first()
        password_ok = (
            organization is not None
            and organization.check_password(password)
            and organization.is_active
        )

        if not password_ok:
            record_attempt(email, ctx['ip'], successful=False, user_agent=ctx['user_agent'])
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not organization.is_verified:
            # A correct password, so this is not a brute-force signal and is not
            # recorded as a failure.
            return Response(
                {'detail': 'Please verify your email address before signing in.',
                 'code': 'email_not_verified'},
                status=status.HTTP_403_FORBIDDEN,
            )

        record_attempt(email, ctx['ip'], successful=True, user_agent=ctx['user_agent'])
        clear_account_failures(email)

        access, refresh = issue_tokens(
            organization, ip=ctx['ip'], user_agent=ctx['user_agent']
        )

        response = Response({
            'access_token': access,
            'organization': OrganizationSerializer(organization).data,
        })
        set_refresh_cookie(response, refresh)
        return response


class RefreshTokenView(APIView):
    """FR-1.5, NFR-1.6 — rotate the refresh token."""

    permission_classes = [AllowAny]

    def post(self, request):
        ctx = _request_context(request)
        try:
            organization, access, refresh = rotate_tokens(
                read_refresh_cookie(request),
                ip=ctx['ip'],
                user_agent=ctx['user_agent'],
            )
        except InvalidRefreshToken as exc:
            response = Response(
                {'detail': str(exc), 'code': 'invalid_refresh_token'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response

        response = Response({
            'access_token': access,
            'organization': OrganizationSerializer(organization).data,
        })
        set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    """FR-1.7 — end the session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoke_refresh_token(read_refresh_cookie(request))
        response = Response({'detail': 'Signed out.'})
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    """The signed-in organisation, for hydrating the SPA after a reload."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(OrganizationSerializer(request.user).data)


# ─── Password reset (FR-1.8, FR-1.9) ─────────────────────────────────────────

@limit('request_password_reset')
class RequestPasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = Organization.objects.filter(
            email=serializer.validated_data['email']
        ).first()

        if organization is not None:
            code = PasswordResetCode.issue(organization)
            _send_async(
                'accounts.tasks.send_password_reset_email', str(organization.id), code.code
            )

        return Response(GENERIC_CODE_SENT)


@limit('verify_password_reset')
class VerifyPasswordResetView(APIView):
    """Check a reset code without consuming it, so the UI can show step two."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = _find_reset_code(
            serializer.validated_data['email'], serializer.validated_data['code']
        )
        if record is None:
            return Response(
                {'detail': 'Invalid or expired reset code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'detail': 'Code accepted. You can now set a new password.'})


@limit('reset_password')
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = _find_reset_code(
            serializer.validated_data['email'], serializer.validated_data['code']
        )
        if record is None:
            return Response(
                {'detail': 'Invalid or expired reset code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = record.organization

        with transaction.atomic():
            record.consume()
            organization.set_password(serializer.validated_data['new_password'])
            organization.save(update_fields=['password', 'updated_at'])
            # Whoever forced this reset must not keep a session from before it.
            revoke_all_sessions(organization)
            clear_account_failures(organization.email)

        response = Response({
            'detail': 'Password updated. All other sessions have been signed out.'
        })
        clear_refresh_cookie(response)
        return response


@limit('request_password_reset')
class ResendPasswordResetView(APIView):
    """FR-1.9 — reissue a reset code."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization = Organization.objects.filter(
            email=serializer.validated_data['email']
        ).first()

        if organization is not None:
            code = PasswordResetCode.issue(organization)
            _send_async(
                'accounts.tasks.send_password_reset_email', str(organization.id), code.code
            )

        return Response(GENERIC_CODE_SENT)


def _find_reset_code(email: str, code: str):
    organization = Organization.objects.filter(email=email).first()
    if organization is None:
        return None

    record = (
        PasswordResetCode.objects
        .filter(organization=organization, code=code)
        .order_by('-created_at')
        .first()
    )
    return record if record is not None and record.is_usable else None
