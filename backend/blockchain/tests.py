"""
Blockchain integration tests (Implementation Plan, Phase 5).

web3 is mocked throughout. The contract's own behaviour — access control,
duplicate rejection, the zero-value struct for an unknown key — is already
proven by the 30 Hardhat tests in blockchain/test/, which run against a real
EVM. Re-asserting it here through a mock would only test the mock. What these
tests cover is the Django side: that a failure becomes a FAILED certificate
with a reason, that every attempt is logged, and that retry recovers.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from blockchain.models import BlockchainInteractionLog, InteractionType
from blockchain.service import (
    BlockchainError,
    BlockchainNotConfigured,
    BlockchainService,
    OnChainCertificate,
    TxResult,
)
from certificates.models import Certificate, CertificateStatus, RevocationLog
from certificates.tasks import (
    expire_certificates,
    flag_stale_pending,
    process_issuance,
    process_revocation,
)

pytestmark = pytest.mark.django_db

ZERO_ADDRESS = '0x' + '0' * 40
ISSUER_ADDRESS = '0x1111111111111111111111111111111111111111'


def make_tx(tx_hash='0x' + 'cd' * 32, block=987654, gas=142_000):
    return TxResult(tx_hash=tx_hash, block_number=block, gas_used=gas)


def make_record(cert_hash, *, revoked=False, exists=True, issuer=ISSUER_ADDRESS):
    return OnChainCertificate(
        cert_hash=cert_hash,
        issuer=issuer if exists else ZERO_ADDRESS,
        issued_at=1_700_000_000 if exists else 0,
        revoked=revoked,
        exists=exists,
    )


@pytest.fixture
def chain():
    """A configured, cooperative BlockchainService."""
    service = MagicMock(spec=BlockchainService)
    service.is_configured.return_value = True
    service.issue_certificate.return_value = make_tx()
    service.revoke_certificate.return_value = make_tx(tx_hash='0x' + 'ef' * 32)

    with patch('certificates.tasks.get_service', return_value=service):
        yield service


@pytest.fixture
def pending_certificate(organization):
    from certificates.hashing import compute_certificate_hash

    cert = Certificate.objects.create(
        organization=organization,
        recipient_name='Ada Lovelace',
        recipient_email='ada@example.com',
        course_title='Introduction to Blockchain',
        issue_date=date.today(),
        expiry_date=date.today() + timedelta(days=365),
        status=CertificateStatus.PENDING,
    )
    cert.certificate_hash = compute_certificate_hash(cert)
    cert.save(update_fields=['certificate_hash'])
    return cert


@pytest.fixture(autouse=True)
def no_email_queue():
    with patch('certificates.tasks._queue_issuance_email'):
        yield


# ─── Key derivation ──────────────────────────────────────────────────────────

class TestKeyDerivation:
    def test_cert_id_hash_is_keccak256_of_the_id(self):
        from web3 import Web3

        digest = BlockchainService.cert_id_hash('CERT-ABC123')

        assert digest == Web3.keccak(text='CERT-ABC123')
        assert len(digest) == 32

    def test_different_ids_give_different_keys(self):
        assert (
            BlockchainService.cert_id_hash('CERT-A')
            != BlockchainService.cert_id_hash('CERT-B')
        )

    def test_rejects_a_hash_that_is_not_32_bytes(self):
        with pytest.raises(BlockchainError, match='32-byte'):
            BlockchainService._to_bytes32('0xdeadbeef')

    def test_accepts_a_hash_with_or_without_prefix(self):
        bare = 'ab' * 32
        assert BlockchainService._to_bytes32(bare) == BlockchainService._to_bytes32(
            '0x' + bare
        )

    def test_explorer_url_points_at_the_transaction(self):
        tx = '0x' + 'ab' * 32
        assert BlockchainService.explorer_tx_url(tx) == (
            f'{settings.BLOCKCHAIN_EXPLORER_URL}/tx/{tx}'
        )


class TestConfigurationGuard:
    def test_is_configured_is_false_without_settings(self, settings):
        settings.BLOCKCHAIN_RPC_URL = ''
        settings.BLOCKCHAIN_CONTRACT_ADDRESS = ''
        settings.BLOCKCHAIN_ISSUER_PRIVATE_KEY = ''

        assert BlockchainService.is_configured() is False

    def test_missing_rpc_url_raises_a_clear_error(self, settings):
        settings.BLOCKCHAIN_RPC_URL = ''
        service = BlockchainService()

        with pytest.raises(BlockchainNotConfigured, match='BLOCKCHAIN_RPC_URL'):
            _ = service.w3


# ─── Issuance (FR-2.5 – FR-2.8) ──────────────────────────────────────────────

class TestIssuance:
    def test_success_promotes_pending_to_valid(self, pending_certificate, chain):
        assert process_issuance(pending_certificate.certificate_id) is True

        pending_certificate.refresh_from_db()
        assert pending_certificate.status == CertificateStatus.VALID
        assert pending_certificate.blockchain_tx_hash == '0x' + 'cd' * 32
        assert pending_certificate.blockchain_block_number == 987654
        assert pending_certificate.anchored_at is not None

    def test_anchors_the_stored_canonical_hash(self, pending_certificate, chain):
        process_issuance(pending_certificate.certificate_id)

        chain.issue_certificate.assert_called_once_with(
            pending_certificate.certificate_id,
            pending_certificate.certificate_hash,
        )

    def test_logs_a_successful_interaction(self, pending_certificate, chain):
        process_issuance(pending_certificate.certificate_id)

        log = BlockchainInteractionLog.objects.get()
        assert log.interaction_type == InteractionType.ISSUE
        assert log.succeeded is True
        assert log.tx_hash == '0x' + 'cd' * 32
        assert log.gas_used == 142_000
        assert log.duration_ms is not None

    def test_failure_marks_the_certificate_failed_with_a_reason(
        self, pending_certificate, chain
    ):
        chain.issue_certificate.side_effect = BlockchainError('insufficient funds for gas')

        assert process_issuance(pending_certificate.certificate_id) is False

        pending_certificate.refresh_from_db()
        assert pending_certificate.status == CertificateStatus.FAILED
        assert 'insufficient funds' in pending_certificate.failure_reason
        assert pending_certificate.blockchain_tx_hash == ''

    def test_failure_is_logged_with_succeeded_false(self, pending_certificate, chain):
        chain.issue_certificate.side_effect = BlockchainError('nonce too low')

        process_issuance(pending_certificate.certificate_id)

        log = BlockchainInteractionLog.objects.get()
        assert log.succeeded is False
        assert 'nonce too low' in log.error_message

    def test_unconfigured_chain_fails_the_certificate_rather_than_crashing(
        self, pending_certificate
    ):
        service = MagicMock(spec=BlockchainService)
        service.is_configured.return_value = False

        with patch('certificates.tasks.get_service', return_value=service):
            assert process_issuance(pending_certificate.certificate_id) is False

        pending_certificate.refresh_from_db()
        assert pending_certificate.status == CertificateStatus.FAILED
        assert 'not configured' in pending_certificate.failure_reason

    def test_task_never_raises(self, pending_certificate, chain):
        """An escaping exception would leave the certificate PENDING forever."""
        chain.issue_certificate.side_effect = RuntimeError('totally unexpected')

        assert process_issuance(pending_certificate.certificate_id) is False

    def test_already_valid_certificate_is_not_anchored_twice(
        self, valid_certificate, chain
    ):
        assert process_issuance(valid_certificate.certificate_id) is False

        # A second anchor would revert with CertificateAlreadyExists.
        chain.issue_certificate.assert_not_called()

    def test_unknown_certificate_is_a_no_op(self, chain):
        assert process_issuance('CERT-NOSUCHTHING') is False

    def test_increments_the_attempt_counter(self, pending_certificate, chain):
        chain.issue_certificate.side_effect = BlockchainError('boom')
        process_issuance(pending_certificate.certificate_id)

        pending_certificate.refresh_from_db()
        assert pending_certificate.issuance_attempts == 1

    def test_already_expired_certificate_skips_valid(self, organization, chain):
        from certificates.hashing import compute_certificate_hash

        cert = Certificate.objects.create(
            organization=organization, recipient_name='Late Arrival',
            recipient_email='late@example.com', course_title='Backdated Course',
            issue_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=1),
            status=CertificateStatus.PENDING,
        )
        cert.certificate_hash = compute_certificate_hash(cert)
        cert.save(update_fields=['certificate_hash'])

        process_issuance(cert.certificate_id)

        cert.refresh_from_db()
        assert cert.status == CertificateStatus.EXPIRED


# ─── Retry (FR-2.9) ──────────────────────────────────────────────────────────

class TestRetry:
    def test_retry_after_failure_reaches_valid(self, auth_client, pending_certificate, chain):
        chain.issue_certificate.side_effect = BlockchainError('RPC timeout')
        process_issuance(pending_certificate.certificate_id)

        pending_certificate.refresh_from_db()
        assert pending_certificate.status == CertificateStatus.FAILED

        response = auth_client.post(
            reverse('certificate-retry', args=[pending_certificate.certificate_id])
        )
        assert response.status_code == 202

        chain.issue_certificate.side_effect = None
        chain.issue_certificate.return_value = make_tx()
        assert process_issuance(pending_certificate.certificate_id) is True

        pending_certificate.refresh_from_db()
        assert pending_certificate.status == CertificateStatus.VALID
        assert pending_certificate.failure_reason == ''

    def test_both_attempts_are_logged(self, pending_certificate, chain):
        chain.issue_certificate.side_effect = BlockchainError('first failure')
        process_issuance(pending_certificate.certificate_id)

        chain.issue_certificate.side_effect = None
        process_issuance(pending_certificate.certificate_id)

        logs = BlockchainInteractionLog.objects.order_by('created_at')
        assert logs.count() == 2
        assert [log.succeeded for log in logs] == [False, True]

    def test_stale_pending_is_flagged(self, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Stuck',
            recipient_email='stuck@example.com', course_title='Course',
            issue_date=date.today(), status=CertificateStatus.PENDING,
        )
        Certificate.objects.filter(pk=cert.pk).update(
            created_at=timezone.now() - timedelta(
                minutes=settings.STALE_PENDING_MINUTES + 5
            )
        )

        assert flag_stale_pending() == 1

        cert.refresh_from_db()
        assert cert.is_retryable is True

    def test_fresh_pending_is_not_flagged(self, pending_certificate):
        assert flag_stale_pending() == 0
        assert pending_certificate.is_retryable is False


# ─── Revocation (FR-3.4, FR-3.5) ─────────────────────────────────────────────

class TestRevocation:
    def _stage(self, certificate, organization):
        return RevocationLog.objects.create(
            certificate=certificate,
            revoked_by=organization,
            reason='Issued in error',
        )

    def test_success_sets_revoked_in_both_places(
        self, valid_certificate, organization, chain
    ):
        log = self._stage(valid_certificate, organization)

        assert process_revocation(valid_certificate.certificate_id) is True

        valid_certificate.refresh_from_db()
        log.refresh_from_db()
        assert valid_certificate.status == CertificateStatus.REVOKED
        assert log.confirmed_on_chain is True
        assert log.blockchain_tx_hash == '0x' + 'ef' * 32

    def test_contract_revert_does_not_silently_succeed(
        self, valid_certificate, organization, chain
    ):
        """
        The contract's issuer-only rule is proven by the Phase 1 suite; what
        matters here is that a revert surfaces instead of the database claiming
        a revocation that never happened on-chain.
        """
        chain.revoke_certificate.side_effect = BlockchainError(
            'execution reverted: NotOriginalIssuer'
        )
        log = self._stage(valid_certificate, organization)

        assert process_revocation(valid_certificate.certificate_id) is False

        valid_certificate.refresh_from_db()
        log.refresh_from_db()
        assert valid_certificate.status == CertificateStatus.VALID, (
            'database must not show REVOKED when the chain refused'
        )
        assert log.confirmed_on_chain is False
        assert 'NotOriginalIssuer' in log.failure_reason

    def test_failure_is_logged(self, valid_certificate, organization, chain):
        chain.revoke_certificate.side_effect = BlockchainError('reverted')
        self._stage(valid_certificate, organization)

        process_revocation(valid_certificate.certificate_id)

        log = BlockchainInteractionLog.objects.get(
            interaction_type=InteractionType.REVOKE
        )
        assert log.succeeded is False

    def test_missing_revocation_log_is_a_no_op(self, valid_certificate, chain):
        assert process_revocation(valid_certificate.certificate_id) is False
        chain.revoke_certificate.assert_not_called()

    def test_revocation_invalidates_the_verification_cache(
        self, valid_certificate, organization, chain
    ):
        from django.core.cache import cache

        from certificates.verification import _revoked_key

        cache.set(_revoked_key(valid_certificate.certificate_id), False, 60)
        self._stage(valid_certificate, organization)

        process_revocation(valid_certificate.certificate_id)

        # Without explicit invalidation the public page would keep answering
        # "not revoked" for up to the 60-second TTL.
        assert cache.get(_revoked_key(valid_certificate.certificate_id)) is None


# ─── Expiration (FR-4.2, FR-4.2.1) ───────────────────────────────────────────

class TestExpiration:
    def test_past_expiry_becomes_expired(self, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Old Cert',
            recipient_email='old@example.com', course_title='Lapsed Course',
            issue_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=1),
            status=CertificateStatus.VALID,
        )

        assert expire_certificates() == 1

        cert.refresh_from_db()
        assert cert.status == CertificateStatus.EXPIRED

    def test_future_expiry_is_untouched(self, valid_certificate):
        assert expire_certificates() == 0

        valid_certificate.refresh_from_db()
        assert valid_certificate.status == CertificateStatus.VALID

    def test_null_expiry_never_expires(self, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Forever',
            recipient_email='f@example.com', course_title='Perpetual Course',
            issue_date=date.today(), expiry_date=None,
            status=CertificateStatus.VALID,
        )

        expire_certificates()

        cert.refresh_from_db()
        assert cert.status == CertificateStatus.VALID

    def test_revoked_certificates_are_not_re_expired(self, organization):
        cert = Certificate.objects.create(
            organization=organization, recipient_name='Gone',
            recipient_email='g@example.com', course_title='Course',
            issue_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=1),
            status=CertificateStatus.REVOKED,
        )

        expire_certificates()

        # Revocation is terminal (FR-4.4).
        cert.refresh_from_db()
        assert cert.status == CertificateStatus.REVOKED

    def test_management_command_runs(self, organization):
        from io import StringIO

        from django.core.management import call_command

        Certificate.objects.create(
            organization=organization, recipient_name='Old Cert',
            recipient_email='old@example.com', course_title='Lapsed',
            issue_date=date.today() - timedelta(days=400),
            expiry_date=date.today() - timedelta(days=1),
            status=CertificateStatus.VALID,
        )

        out = StringIO()
        call_command('expire_certificates', stdout=out)

        assert 'Expired 1' in out.getvalue()


# ─── Worker configuration ────────────────────────────────────────────────────

class TestWorkerConfiguration:
    def test_cluster_runs_a_single_worker(self):
        """
        Guards the nonce-collision fix.

        Two workers would both read the same pending nonce and one transaction
        would be dropped, stranding a certificate as PENDING. If someone raises
        this for throughput, this test is the explanation waiting for them.
        """
        assert settings.Q_CLUSTER['workers'] == 1
