"""
Background email tasks for authentication.

These go through django-q2 so a slow or unavailable SMTP server cannot hold a
registration request open. With EMAIL_BACKEND left at its development default
the message is written to the console; Phase 8 switches that to SMTP purely by
changing the environment, with no code change here.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Organization

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10


def _deliver(*, organization, subject, body, kind, html_context=None):
    """Send and log. Never raises — a queued task must not crash the cluster."""
    from notifications.models import NotificationLog, NotificationStatus

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[organization.email],
    )
    # The plain-text body stays the source of truth: it is what plain-text
    # clients and screen readers get, and it must carry the code on its own.
    if html_context:
        message.attach_alternative(
            render_to_string('emails/code_email.html', html_context), 'text/html'
        )

    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001
        logger.error('Failed to send %s to %s: %s', kind, organization.email, exc)
        NotificationLog.objects.create(
            kind=kind,
            recipient_email=organization.email,
            subject=subject,
            status=NotificationStatus.FAILED,
            error_message=str(exc)[:2000],
        )
        return False

    logger.info('Sent %s to %s', kind, organization.email)
    NotificationLog.objects.create(
        kind=kind,
        recipient_email=organization.email,
        subject=subject,
        status=NotificationStatus.SENT,
    )
    return True


def send_verification_email(organization_id: str, code: str) -> bool:
    from notifications.models import NotificationKind

    organization = Organization.objects.filter(pk=organization_id).first()
    if organization is None:
        logger.error('send_verification_email: no organisation %s', organization_id)
        return False

    body = (
        f'Hello {organization.name},\n\n'
        f'Your BCIP email verification code is:\n\n'
        f'    {code}\n\n'
        f'It expires in {CODE_TTL_MINUTES} minutes and can be used once.\n\n'
        f'If you did not create a BCIP account, you can ignore this message.\n'
    )

    return _deliver(
        organization=organization,
        subject='Verify your BCIP account',
        body=body,
        kind=NotificationKind.EMAIL_VERIFICATION,
        html_context={
            'heading': 'Verify your email address',
            'greeting_name': organization.name,
            'intro': 'Use the code below to finish setting up your BCIP account.',
            'code': code,
            'ttl_minutes': CODE_TTL_MINUTES,
            'disclaimer': 'If you did not create a BCIP account, you can safely '
                          'ignore this message.',
            'preheader': f'Your BCIP verification code expires in '
                         f'{CODE_TTL_MINUTES} minutes.',
        },
    )


def send_password_reset_email(organization_id: str, code: str) -> bool:
    from notifications.models import NotificationKind

    organization = Organization.objects.filter(pk=organization_id).first()
    if organization is None:
        logger.error('send_password_reset_email: no organisation %s', organization_id)
        return False

    body = (
        f'Hello {organization.name},\n\n'
        f'Your BCIP password reset code is:\n\n'
        f'    {code}\n\n'
        f'It expires in {CODE_TTL_MINUTES} minutes and can be used once.\n\n'
        f'If you did not request a password reset, ignore this message — your '
        f'password has not changed.\n'
    )

    return _deliver(
        organization=organization,
        subject='Reset your BCIP password',
        body=body,
        kind=NotificationKind.PASSWORD_RESET,
        html_context={
            'heading': 'Reset your password',
            'greeting_name': organization.name,
            'intro': 'Use the code below to set a new password for your BCIP '
                     'account.',
            'code': code,
            'ttl_minutes': CODE_TTL_MINUTES,
            'disclaimer': 'If you did not request a password reset, ignore this '
                          'message — your password has not changed.',
            'preheader': f'Your BCIP password reset code expires in '
                         f'{CODE_TTL_MINUTES} minutes.',
        },
    )


def purge_login_attempts(days: int = 30) -> int:
    """Scheduled housekeeping for the LoginAttempt log (FR-1.6)."""
    from .lockout import purge_old_attempts

    deleted = purge_old_attempts(days)
    logger.info('Purged %s login attempts older than %s days', deleted, days)
    return deleted
