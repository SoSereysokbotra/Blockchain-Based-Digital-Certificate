import random
import string
from datetime import timedelta
from django.utils import timezone
from .models import EmailVerificationCode, PasswordResetCode


def generate_code(length=6):
    """Generate a random numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))


def create_email_verification_code(organization):
    """Create or replace an email verification code for an organization."""
    code = generate_code()
    expires_at = timezone.now() + timedelta(hours=24)
    EmailVerificationCode.objects.update_or_create(
        organization=organization,
        defaults={'code': code, 'expires_at': expires_at}
    )
    return code


def create_password_reset_code(organization):
    """Create a new password reset code (invalidates old ones)."""
    # Mark previous codes as used
    PasswordResetCode.objects.filter(
        organization=organization, used=False
    ).update(used=True)

    code = generate_code()
    expires_at = timezone.now() + timedelta(hours=1)
    PasswordResetCode.objects.create(
        organization=organization,
        code=code,
        expires_at=expires_at
    )
    return code
