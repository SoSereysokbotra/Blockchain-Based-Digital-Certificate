"""
Certificate tests (Implementation Plan, Phases 4–6).

The PDF assertions extract text with pdfplumber and decode the QR with pyzbar
rather than trusting that rendering "looked right". A missing font or a broken
data URI produces a PDF that opens fine and contains no readable text at all —
only extraction catches that.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from certificates.hashing import (
    canonical_payload,
    compute_certificate_hash,
    hashes_match,
)
from certificates.models import Certificate, CertificateStatus, RevocationLog
from certificates.pdf import generate_qr_png, pdf_path_for, verification_url

pytestmark = pytest.mark.django_db


LIST_URL = reverse('certificate-list-create')


def detail_url(certificate_id):
    return reverse('certificate-detail', args=[certificate_id])


def revoke_url(certificate_id):
    return reverse('certificate-revoke', args=[certificate_id])


def retry_url(certificate_id):
    return reverse('certificate-retry', args=[certificate_id])


@pytest.fixture(autouse=True)
def no_real_queue():
    """Never enqueue against a live cluster from the test suite."""
    with patch('django_q.tasks.async_task') as mock:
        yield mock


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return '\n'.join(page.extract_text() or '' for page in pdf.pages)


def decode_qr(png_bytes: bytes) -> list[str]:
    from PIL import Image
    from pyzbar.pyzbar import decode

    return [d.data.decode('utf-8') for d in decode(Image.open(io.BytesIO(png_bytes)))]


# ─── Input validation (FR-2.1.1, FR-2.1.2) ───────────────────────────────────

class TestCertificateValidation:
    def test_creates_with_valid_input(self, auth_client, certificate_payload):
        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 202
        assert response.data['status'] == CertificateStatus.PENDING
        assert response.data['certificate_id'].startswith('CERT-')

    def test_rejects_name_over_200_characters(self, auth_client, certificate_payload):
        certificate_payload['recipient_name'] = 'A' * 201

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400
        assert 'recipient_name' in response.data

    def test_accepts_name_at_exactly_200_characters(self, auth_client, certificate_payload):
        certificate_payload['recipient_name'] = 'A' * 200

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 202

    def test_rejects_title_over_200_characters(self, auth_client, certificate_payload):
        certificate_payload['course_title'] = 'B' * 201

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400
        assert 'course_title' in response.data

    def test_rejects_html_in_title(self, auth_client, certificate_payload):
        certificate_payload['course_title'] = 'Intro <script>alert(1)</script>'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400
        assert 'course_title' in response.data

    def test_rejects_html_in_recipient_name(self, auth_client, certificate_payload):
        certificate_payload['recipient_name'] = '<img src=x onerror=alert(1)>'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400

    def test_rejects_javascript_uri(self, auth_client, certificate_payload):
        certificate_payload['course_title'] = 'javascript:alert(document.cookie)'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400

    def test_rejects_spreadsheet_formula_prefix(self, auth_client, certificate_payload):
        # Certificate lists get exported to CSV; a leading '=' is executed by
        # Excel and Sheets.
        certificate_payload['recipient_name'] = '=cmd|/c calc'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400

    def test_rejects_email_over_254_characters(self, auth_client, certificate_payload):
        certificate_payload['recipient_email'] = 'a' * 250 + '@example.com'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400
        assert 'recipient_email' in response.data

    def test_rejects_malformed_email(self, auth_client, certificate_payload):
        certificate_payload['recipient_email'] = 'not-an-email'

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400

    def test_rejects_expiry_before_issue_date(self, auth_client, certificate_payload):
        certificate_payload['expiry_date'] = str(date.today() - timedelta(days=1))

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 400
        assert 'expiry_date' in response.data

    def test_allows_null_expiry(self, auth_client, certificate_payload):
        certificate_payload['expiry_date'] = None

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 202

    def test_normalises_whitespace(self, auth_client, certificate_payload):
        certificate_payload['recipient_name'] = '  Ada   Lovelace  '

        response = auth_client.post(LIST_URL, certificate_payload, format='json')

        cert = Certificate.objects.get(certificate_id=response.data['certificate_id'])
        assert cert.recipient_name == 'Ada Lovelace'

    def test_requires_authentication(self, api, certificate_payload):
        assert api.post(LIST_URL, certificate_payload, format='json').status_code == 401


# ─── PDF and QR (FR-2.3, FR-5.2) ─────────────────────────────────────────────

class TestPdfGeneration:
    def _create(self, auth_client, payload):
        response = auth_client.post(LIST_URL, payload, format='json')
        assert response.status_code == 202
        return Certificate.objects.get(certificate_id=response.data['certificate_id'])

    def test_pdf_file_is_written(self, auth_client, certificate_payload):
        cert = self._create(auth_client, certificate_payload)

        assert cert.pdf_url == f'pdfs/{cert.certificate_id}.pdf'
        assert pdf_path_for(cert.certificate_id).exists()

    def test_pdf_contains_all_required_text(self, auth_client, certificate_payload):
        """FR-2.3 — checked by extraction, not by eye."""
        cert = self._create(auth_client, certificate_payload)
        text = extract_pdf_text(pdf_path_for(cert.certificate_id).read_bytes())

        assert cert.recipient_name in text
        assert cert.course_title in text
        assert cert.certificate_id in text
        assert cert.issue_date.strftime('%Y') in text
        # The issuer line is styled `text-transform: uppercase`, which WeasyPrint
        # applies before the glyphs are written, so compare case-insensitively.
        assert cert.organization.name.upper() in text.upper()

    def test_pdf_records_its_own_digest(self, auth_client, certificate_payload):
        import hashlib

        cert = self._create(auth_client, certificate_payload)
        raw = pdf_path_for(cert.certificate_id).read_bytes()

        assert cert.pdf_sha256 == '0x' + hashlib.sha256(raw).hexdigest()

    def test_qr_decodes_to_the_verification_url(self, auth_client, certificate_payload):
        cert = self._create(auth_client, certificate_payload)
        decoded = decode_qr(generate_qr_png(cert.certificate_id))

        assert decoded == [f'{settings.FRONTEND_URL}/verify/{cert.certificate_id}']

    def test_qr_url_matches_the_public_route(self, valid_certificate):
        assert verification_url(valid_certificate.certificate_id).endswith(
            f'/verify/{valid_certificate.certificate_id}'
        )

    def test_pdf_survives_unicode_names(self, auth_client, certificate_payload):
        certificate_payload['recipient_name'] = 'Zoë Białystok-Ñuñez'

        cert = self._create(auth_client, certificate_payload)
        text = extract_pdf_text(pdf_path_for(cert.certificate_id).read_bytes())

        # A missing font would render these as blank boxes and drop them here.
        assert 'Zo' in text and 'Bia' in text

    def test_pdf_failure_does_not_lose_the_certificate(self, auth_client, certificate_payload):
        with patch('certificates.services.generate_and_store_pdf',
                   side_effect=RuntimeError('pango exploded')):
            response = auth_client.post(LIST_URL, certificate_payload, format='json')

        assert response.status_code == 202
        cert = Certificate.objects.get(certificate_id=response.data['certificate_id'])
        assert cert.certificate_hash, 'hash must survive a PDF failure'
        assert 'pango exploded' in cert.failure_reason


# ─── Idempotency (FR-2.2.1) ──────────────────────────────────────────────────

class TestIdempotency:
    def test_same_key_returns_the_same_certificate(self, auth_client, certificate_payload):
        key = str(uuid.uuid4())

        first = auth_client.post(LIST_URL, certificate_payload, format='json',
                                 HTTP_IDEMPOTENCY_KEY=key)
        second = auth_client.post(LIST_URL, certificate_payload, format='json',
                                  HTTP_IDEMPOTENCY_KEY=key)

        assert first.status_code == second.status_code == 202
        assert first.data['certificate_id'] == second.data['certificate_id']
        assert Certificate.objects.count() == 1

    def test_second_call_does_not_enqueue_again(self, auth_client, certificate_payload,
                                                no_real_queue):
        key = str(uuid.uuid4())
        auth_client.post(LIST_URL, certificate_payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=key)
        auth_client.post(LIST_URL, certificate_payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=key)

        # Anchoring twice would revert on-chain with CertificateAlreadyExists.
        assert no_real_queue.call_count == 1

    def test_different_keys_create_different_certificates(self, auth_client,
                                                          certificate_payload):
        auth_client.post(LIST_URL, certificate_payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        auth_client.post(LIST_URL, certificate_payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        assert Certificate.objects.count() == 2

    def test_no_key_always_creates(self, auth_client, certificate_payload):
        auth_client.post(LIST_URL, certificate_payload, format='json')
        auth_client.post(LIST_URL, certificate_payload, format='json')

        assert Certificate.objects.count() == 2

    def test_idempotency_key_header_survives_cors_preflight(self, api):
        """
        The browser will not send the POST at all unless the preflight allows
        this custom header, and the failure is invisible server-side: the log
        shows an OPTIONS with no POST after it, and the UI shows only a generic
        "failed, please try again". Asserting the allow-list here is the cheapest
        way to stop that recurring.
        """
        from django.conf import settings

        allowed = [h.lower() for h in settings.CORS_ALLOW_HEADERS]
        assert 'idempotency-key' in allowed

        response = api.options(
            LIST_URL,
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type,authorization,idempotency-key',
        )

        assert 'idempotency-key' in response['access-control-allow-headers'].lower()

    def test_key_is_scoped_per_organization(self, auth_client, other_auth_client,
                                            certificate_payload):
        key = str(uuid.uuid4())

        auth_client.post(LIST_URL, certificate_payload, format='json',
                         HTTP_IDEMPOTENCY_KEY=key)
        other = other_auth_client.post(LIST_URL, certificate_payload, format='json',
                                       HTTP_IDEMPOTENCY_KEY=key)

        # One tenant's key must not collide with another's, or a rival could
        # probe for issued certificates by guessing keys.
        assert other.status_code == 202
        assert Certificate.objects.count() == 2


# ─── Canonical hashing (SRS 7.2.1) ───────────────────────────────────────────

class TestCanonicalHashing:
    def test_is_deterministic(self, valid_certificate):
        assert compute_certificate_hash(valid_certificate) == compute_certificate_hash(
            valid_certificate
        )

    def test_is_32_bytes_of_hex(self, valid_certificate):
        digest = compute_certificate_hash(valid_certificate)

        assert digest.startswith('0x')
        assert len(digest) == 66
        int(digest, 16)  # raises if not hex

    @pytest.mark.parametrize('field,new_value', [
        ('recipient_name', 'Mallory Attacker'),
        ('recipient_email', 'mallory@example.com'),
        ('course_title', 'Advanced Forgery'),
        ('issue_date', date(2020, 1, 1)),
        ('expiry_date', date(2099, 1, 1)),
    ])
    def test_changing_any_field_changes_the_hash(self, valid_certificate, field, new_value):
        before = compute_certificate_hash(valid_certificate)
        setattr(valid_certificate, field, new_value)

        assert compute_certificate_hash(valid_certificate) != before

    def test_clearing_expiry_changes_the_hash(self, valid_certificate):
        before = compute_certificate_hash(valid_certificate)
        valid_certificate.expiry_date = None

        assert compute_certificate_hash(valid_certificate) != before

    def test_none_expiry_is_null_not_empty_string(self, valid_certificate):
        valid_certificate.expiry_date = None

        assert canonical_payload(valid_certificate)['expiryDate'] is None

    def test_dates_serialise_without_a_time_component(self, valid_certificate):
        payload = canonical_payload(valid_certificate)

        assert payload['issueDate'] == valid_certificate.issue_date.isoformat()
        assert len(payload['issueDate']) == 10

    def test_payload_is_versioned(self, valid_certificate):
        assert canonical_payload(valid_certificate)['v'] == 1

    def test_hash_comparison_tolerates_prefix_and_case(self):
        bare = 'ab' * 32
        assert hashes_match('0x' + bare, bare.upper())
        assert hashes_match('0x' + bare, '0x' + bare)
        assert not hashes_match('0x' + bare, '0x' + 'cd' * 32)
        assert not hashes_match(None, bare)
        assert not hashes_match('', bare)


# ─── Listing, search and tenant isolation (FR-3.1, FR-3.2, NFR-1.5) ──────────

class TestCertificateListing:
    def test_lists_only_the_callers_certificates(self, auth_client, valid_certificate,
                                                 other_organization):
        Certificate.objects.create(
            organization=other_organization,
            recipient_name='Someone Else',
            recipient_email='else@example.com',
            course_title='Rival Course',
            issue_date=date.today(),
            status=CertificateStatus.VALID,
        )

        response = auth_client.get(LIST_URL)

        assert response.data['count'] == 1
        assert response.data['results'][0]['certificate_id'] == (
            valid_certificate.certificate_id
        )

    def test_cross_organization_detail_returns_404(self, other_auth_client,
                                                   valid_certificate):
        response = other_auth_client.get(detail_url(valid_certificate.certificate_id))

        # 404 rather than 403: a 403 would confirm the ID exists.
        assert response.status_code == 404

    def test_cross_organization_revoke_returns_404(self, other_auth_client,
                                                   valid_certificate):
        response = other_auth_client.post(
            revoke_url(valid_certificate.certificate_id),
            {'reason': 'Not mine to revoke'}, format='json',
        )

        assert response.status_code == 404
        valid_certificate.refresh_from_db()
        assert valid_certificate.status == CertificateStatus.VALID

    def test_cross_organization_retry_returns_404(self, other_auth_client,
                                                  valid_certificate):
        valid_certificate.status = CertificateStatus.FAILED
        valid_certificate.save(update_fields=['status'])

        response = other_auth_client.post(retry_url(valid_certificate.certificate_id))

        assert response.status_code == 404

    def test_search_by_recipient_name(self, auth_client, organization, valid_certificate):
        Certificate.objects.create(
            organization=organization, recipient_name='Alan Turing',
            recipient_email='alan@example.com', course_title='Computability',
            issue_date=date.today(), status=CertificateStatus.VALID,
        )

        response = auth_client.get(LIST_URL, {'search': 'Turing'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['recipient_name'] == 'Alan Turing'

    def test_search_by_certificate_id(self, auth_client, valid_certificate):
        response = auth_client.get(
            LIST_URL, {'search': valid_certificate.certificate_id}
        )

        assert response.data['count'] == 1

    def test_filter_by_status(self, auth_client, organization, valid_certificate):
        Certificate.objects.create(
            organization=organization, recipient_name='Pending Person',
            recipient_email='p@example.com', course_title='Queued Course',
            issue_date=date.today(), status=CertificateStatus.PENDING,
        )

        response = auth_client.get(LIST_URL, {'status': 'PENDING'})

        assert response.data['count'] == 1
        assert response.data['results'][0]['status'] == 'PENDING'

    def test_pagination_uses_a_page_size_of_25(self, auth_client, organization):
        Certificate.objects.bulk_create([
            Certificate(
                organization=organization, recipient_name=f'Person {i}',
                recipient_email=f'p{i}@example.com', course_title='Bulk Course',
                issue_date=date.today(), status=CertificateStatus.VALID,
                certificate_id=f'CERT-BULK{i:08d}',
            )
            for i in range(30)
        ])

        response = auth_client.get(LIST_URL)

        assert response.data['count'] == 30
        assert len(response.data['results']) == 25
        assert response.data['next'] is not None

    def test_requires_authentication(self, api):
        assert api.get(LIST_URL).status_code == 401


class TestCertificateDetail:
    def test_returns_the_blockchain_reference(self, auth_client, valid_certificate):
        response = auth_client.get(detail_url(valid_certificate.certificate_id))

        assert response.status_code == 200
        assert response.data['blockchain_tx_hash'] == valid_certificate.blockchain_tx_hash
        assert response.data['explorer_url'].endswith(
            valid_certificate.blockchain_tx_hash
        )

    def test_unknown_id_returns_404(self, auth_client):
        assert auth_client.get(detail_url('CERT-DOESNOTEXIST')).status_code == 404


# ─── Revocation (FR-3.4, FR-3.5) ─────────────────────────────────────────────

class TestRevocation:
    def test_revocation_requires_a_reason(self, auth_client, valid_certificate):
        response = auth_client.post(
            revoke_url(valid_certificate.certificate_id), {}, format='json'
        )

        assert response.status_code == 400
        assert 'reason' in response.data

    def test_revocation_logs_the_reason_and_queues_the_transaction(
        self, auth_client, valid_certificate, no_real_queue
    ):
        response = auth_client.post(
            revoke_url(valid_certificate.certificate_id),
            {'reason': 'Issued to the wrong recipient'}, format='json',
        )

        assert response.status_code == 202
        log = RevocationLog.objects.get(certificate=valid_certificate)
        assert log.reason == 'Issued to the wrong recipient'
        assert log.confirmed_on_chain is False
        assert no_real_queue.called

    def test_cannot_revoke_a_pending_certificate(self, auth_client, valid_certificate):
        valid_certificate.status = CertificateStatus.PENDING
        valid_certificate.save(update_fields=['status'])

        response = auth_client.post(
            revoke_url(valid_certificate.certificate_id),
            {'reason': 'Too early'}, format='json',
        )

        assert response.status_code == 409

    def test_cannot_revoke_twice(self, auth_client, valid_certificate):
        valid_certificate.status = CertificateStatus.REVOKED
        valid_certificate.save(update_fields=['status'])

        response = auth_client.post(
            revoke_url(valid_certificate.certificate_id),
            {'reason': 'Again'}, format='json',
        )

        assert response.status_code == 409


# ─── Retry eligibility (FR-2.9) ──────────────────────────────────────────────

class TestRetryEligibility:
    def test_failed_certificate_is_retryable(self, auth_client, valid_certificate):
        valid_certificate.status = CertificateStatus.FAILED
        valid_certificate.failure_reason = 'insufficient funds'
        valid_certificate.save(update_fields=['status', 'failure_reason'])

        response = auth_client.post(retry_url(valid_certificate.certificate_id))

        assert response.status_code == 202
        valid_certificate.refresh_from_db()
        assert valid_certificate.status == CertificateStatus.PENDING
        assert valid_certificate.failure_reason == ''

    def test_fresh_pending_is_not_retryable(self, auth_client, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Just Queued',
            recipient_email='jq@example.com', course_title='Course',
            issue_date=date.today(), status=CertificateStatus.PENDING,
        )

        response = auth_client.post(retry_url(cert.certificate_id))

        assert response.status_code == 409

    def test_stale_pending_becomes_retryable(self, auth_client, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Stuck Forever',
            recipient_email='sf@example.com', course_title='Course',
            issue_date=date.today(), status=CertificateStatus.PENDING,
        )
        # created_at is auto_now_add, so age it directly.
        Certificate.objects.filter(pk=cert.pk).update(
            created_at=timezone.now() - timedelta(
                minutes=settings.STALE_PENDING_MINUTES + 1
            )
        )
        cert.refresh_from_db()

        assert cert.is_retryable is True
        assert auth_client.post(retry_url(cert.certificate_id)).status_code == 202

    def test_valid_certificate_is_not_retryable(self, auth_client, valid_certificate):
        assert auth_client.post(
            retry_url(valid_certificate.certificate_id)
        ).status_code == 409
