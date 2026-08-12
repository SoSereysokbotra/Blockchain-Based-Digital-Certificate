"""
Shared pytest fixtures.

The cache deserves a note. CACHES is DatabaseCache in every environment,
including tests, because the rate-limit assertions are only meaningful against
the backend that actually runs in production — a LocMemCache override here would
make the tests pass while the deployed thresholds silently multiplied by the
worker count. `clear_cache` therefore wipes real rows between tests so
per-test rate-limit counters start from zero.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from certificates.models import Certificate, CertificateStatus

PASSWORD = 'CorrectHorse!2026'


@pytest.fixture(autouse=True)
def clear_cache(db):
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def organization(db):
    return Organization.objects.create_user(
        email='issuer@example.edu',
        name='Example Institute',
        password=PASSWORD,
        is_verified=True,
        wallet_address='0x1111111111111111111111111111111111111111',
    )


@pytest.fixture
def other_organization(db):
    """A second tenant, for cross-organisation isolation tests (NFR-1.5)."""
    return Organization.objects.create_user(
        email='rival@example.edu',
        name='Rival Academy',
        password=PASSWORD,
        is_verified=True,
        wallet_address='0x2222222222222222222222222222222222222222',
    )


@pytest.fixture
def unverified_organization(db):
    return Organization.objects.create_user(
        email='pending@example.edu',
        name='Pending Institute',
        password=PASSWORD,
        is_verified=False,
    )


@pytest.fixture
def auth_client(api, organization):
    """APIClient carrying a valid access token for `organization`."""
    from accounts.tokens import issue_tokens

    access, _refresh = issue_tokens(organization)
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return api


@pytest.fixture
def other_auth_client(other_organization):
    from accounts.tokens import issue_tokens

    client = APIClient()
    access, _refresh = issue_tokens(other_organization)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client


@pytest.fixture
def certificate_payload():
    return {
        'recipient_name': 'Ada Lovelace',
        'recipient_email': 'ada@example.com',
        'course_title': 'Introduction to Blockchain',
        'issue_date': str(date.today()),
        'expiry_date': str(date.today() + timedelta(days=365)),
    }


@pytest.fixture
def valid_certificate(organization):
    """An already-anchored certificate, as issuance would leave it."""
    from certificates.hashing import compute_certificate_hash

    cert = Certificate.objects.create(
        organization=organization,
        recipient_name='Grace Hopper',
        recipient_email='grace@example.com',
        course_title='Compiler Construction',
        issue_date=date.today() - timedelta(days=10),
        expiry_date=date.today() + timedelta(days=355),
        status=CertificateStatus.VALID,
        blockchain_tx_hash='0x' + 'ab' * 32,
        blockchain_block_number=1234567,
        anchored_at=timezone.now(),
        pdf_url='pdfs/test.pdf',
    )
    cert.certificate_hash = compute_certificate_hash(cert)
    cert.save(update_fields=['certificate_hash'])
    return cert
