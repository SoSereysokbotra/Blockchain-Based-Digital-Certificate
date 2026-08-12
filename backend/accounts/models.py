"""
Identity and authentication models (SRS 6.1).

An Organization is the authenticated principal: BCIP has no separate per-user
account within an organisation (SRS 2.6), so Organization *is* AUTH_USER_MODEL.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

# Verification and password-reset codes expire 10 minutes after generation and
# are single-use (Implementation Plan, Phase 3 / SRS FR-1.1, FR-1.8).
CODE_TTL = timedelta(minutes=10)
CODE_LENGTH = 6


def generate_code(length: int = CODE_LENGTH) -> str:
    """
    Cryptographically secure numeric one-time code.

    `secrets`, not `random`: the Mersenne Twister behind `random` is fully
    predictable from a modest run of prior outputs, which for an account-recovery
    code is an account-takeover primitive.
    """
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def hash_token(raw_token: str) -> str:
    """
    SHA-256 of a refresh token, for at-rest storage (NFR-1.6).

    A plain hash rather than a slow KDF is correct here: the input is a
    128-bit-plus random JWT, not a guessable human password, so there is nothing
    for an attacker to brute-force and the cost of a KDF buys nothing.
    """
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


class OrganizationManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email).lower()
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, name, password, **extra_fields)


class Organization(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True, db_index=True)

    # Blockchain address this organisation issues from. Must be an authorised
    # issuer on CertificateRegistry for its transactions to succeed.
    wallet_address = models.CharField(
        max_length=42,
        blank=True,
        help_text='EVM address (0x…) authorised to issue on the registry contract.',
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(
        default=False,
        help_text='Email ownership confirmed. Login is refused until this is true.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganizationManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'organizations'
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} <{self.email}>'


class OneTimeCode(models.Model):
    """
    Shared behaviour for the two short-lived code types.

    Codes are stored in plaintext deliberately: they live for 10 minutes, are
    single-use, and are delivered to the address being proven. Hashing them
    would prevent the operator from supporting a user over the phone while
    adding no meaningful protection at that lifetime.
    """

    code = models.CharField(max_length=CODE_LENGTH, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_usable(self) -> bool:
        return not self.is_expired and not self.is_used

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])


class EmailVerificationCode(OneTimeCode):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='email_verification_codes',
    )

    class Meta:
        db_table = 'email_verification_codes'
        indexes = [models.Index(fields=['organization', 'code'])]

    def __str__(self):
        return f'Email verification for {self.organization.email}'

    @classmethod
    def issue(cls, organization) -> 'EmailVerificationCode':
        """Invalidate any outstanding codes and mint a fresh one."""
        cls.objects.filter(
            organization=organization, used_at__isnull=True
        ).update(used_at=timezone.now())
        return cls.objects.create(
            organization=organization,
            code=generate_code(),
            expires_at=timezone.now() + CODE_TTL,
        )


class PasswordResetCode(OneTimeCode):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='password_reset_codes',
    )

    class Meta:
        db_table = 'password_reset_codes'
        indexes = [models.Index(fields=['organization', 'code'])]

    def __str__(self):
        return f'Password reset for {self.organization.email}'

    @classmethod
    def issue(cls, organization) -> 'PasswordResetCode':
        cls.objects.filter(
            organization=organization, used_at__isnull=True
        ).update(used_at=timezone.now())
        return cls.objects.create(
            organization=organization,
            code=generate_code(),
            expires_at=timezone.now() + CODE_TTL,
        )


class RefreshToken(models.Model):
    """
    Server-side record of every issued refresh token (NFR-1.6).

    SimpleJWT's blacklist app already handles rotation; this table exists so the
    server can enumerate and revoke an organisation's sessions — specifically,
    so a password reset can invalidate every outstanding session, which the
    blacklist alone cannot do because it only knows about tokens it has seen
    presented.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='refresh_tokens',
    )
    # SHA-256 of the JWT. The raw token is never persisted.
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    jti = models.CharField(max_length=64, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'refresh_tokens'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['organization', 'revoked_at'])]

    def __str__(self):
        return f'Refresh token for {self.organization.email} ({self.jti})'

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and timezone.now() < self.expires_at

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])

    @classmethod
    def record(cls, organization, raw_token, jti, expires_at, *, ip=None, user_agent=''):
        return cls.objects.create(
            organization=organization,
            token_hash=hash_token(str(raw_token)),
            jti=jti,
            expires_at=expires_at,
            ip_address=ip,
            user_agent=(user_agent or '')[:300],
        )

    @classmethod
    def lookup(cls, raw_token):
        return cls.objects.filter(token_hash=hash_token(str(raw_token))).first()

    @classmethod
    def revoke_all_for(cls, organization) -> int:
        return cls.objects.filter(
            organization=organization, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())


class LoginAttempt(models.Model):
    """
    Append-only log of authentication attempts, backing lockout (FR-1.6).

    Lockout is computed by querying this table rather than by keeping a counter
    on Organization, because the IP-based limit has to aggregate across accounts
    that may not exist — a counter column cannot answer "how many failures from
    this IP" when the attacker is guessing email addresses at random.
    """

    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    successful = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'login_attempts'
        ordering = ['-attempted_at']
        indexes = [
            models.Index(fields=['email', 'attempted_at']),
            models.Index(fields=['ip_address', 'attempted_at']),
        ]

    def __str__(self):
        outcome = 'success' if self.successful else 'failure'
        return f'{self.email} from {self.ip_address} — {outcome}'
