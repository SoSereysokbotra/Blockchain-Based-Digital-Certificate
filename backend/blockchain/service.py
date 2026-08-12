"""
The only module in the BCIP backend that imports web3.

Everything the application knows about the chain goes through BlockchainService:
transaction signing, receipt polling, and the read path used by public
verification. Nothing else may import `web3` — SRS 5.5 requires the
blockchain-interaction layer to be separable, and concentrating the signing key
in one module is what makes NFR-1.2 auditable rather than aspirational.

Key facts encoded here:

* Certificates are keyed on-chain by ``keccak256(certificate_id)``. The readable
  ID never leaves PostgreSQL.
* ``getCertificate`` returns a zero-value struct for an unknown key rather than
  reverting, so ``issuer == 0x0`` is the existence test. This is asserted by the
  Phase 1 contract test suite, which is the contract for this behaviour.
* All writes serialise through a single django-q2 worker (see Q_CLUSTER). Two
  processes signing concurrently would both read the same nonce and one
  transaction would be silently dropped.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

ABI_PATH = Path(__file__).resolve().parent / 'abi' / 'CertificateRegistry.json'

# Guards the read-nonce → sign → send window. Within a single-worker cluster
# this is belt-and-braces; it also makes the service safe if someone later runs
# the cluster with more than one thread.
_nonce_lock = threading.Lock()


class BlockchainError(RuntimeError):
    """Any failure interacting with the chain. Carries a human-readable cause."""


class BlockchainNotConfigured(BlockchainError):
    """RPC URL, contract address or signing key missing from the environment."""


@dataclass(frozen=True)
class OnChainCertificate:
    """A CertificateRecord struct read back from the registry."""

    cert_hash: str          # '0x…' 32-byte hex, or '0x00…0' when absent
    issuer: str             # checksummed address, or the zero address
    issued_at: int          # unix seconds, 0 when absent
    revoked: bool
    exists: bool            # issuer != 0x0 — the documented existence rule


@dataclass(frozen=True)
class TxResult:
    tx_hash: str
    block_number: int
    gas_used: int


@lru_cache(maxsize=1)
def _load_abi() -> list:
    with ABI_PATH.open('r', encoding='utf-8') as fh:
        return json.load(fh)


class BlockchainService:
    """Wraps the deployed CertificateRegistry contract."""

    def __init__(self, *, rpc_url=None, contract_address=None, private_key=None):
        self.rpc_url = rpc_url if rpc_url is not None else settings.BLOCKCHAIN_RPC_URL
        self.contract_address = (
            contract_address if contract_address is not None
            else settings.BLOCKCHAIN_CONTRACT_ADDRESS
        )
        self.private_key = (
            private_key if private_key is not None
            else settings.BLOCKCHAIN_ISSUER_PRIVATE_KEY
        )
        self._w3 = None
        self._contract = None
        self._account = None

    # ─── Wiring ───────────────────────────────────────────────────────────────

    @staticmethod
    def is_configured() -> bool:
        return bool(
            settings.BLOCKCHAIN_RPC_URL
            and settings.BLOCKCHAIN_CONTRACT_ADDRESS
            and settings.BLOCKCHAIN_ISSUER_PRIVATE_KEY
        )

    @property
    def w3(self):
        if self._w3 is None:
            from web3 import Web3

            if not self.rpc_url:
                raise BlockchainNotConfigured('BLOCKCHAIN_RPC_URL is not set.')
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={'timeout': 30}))
        return self._w3

    @property
    def contract(self):
        if self._contract is None:
            from web3 import Web3

            if not self.contract_address:
                raise BlockchainNotConfigured('BLOCKCHAIN_CONTRACT_ADDRESS is not set.')
            self._contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=_load_abi(),
            )
        return self._contract

    @property
    def account(self):
        if self._account is None:
            if not self.private_key:
                raise BlockchainNotConfigured('BLOCKCHAIN_ISSUER_PRIVATE_KEY is not set.')
            self._account = self.w3.eth.account.from_key(self.private_key)
        return self._account

    @property
    def issuer_address(self) -> str:
        return self.account.address

    def check_connection(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception as exc:  # noqa: BLE001 — surfaced as a clean error
            raise BlockchainError(f'RPC connection failed: {exc}') from exc

    # ─── Key derivation ───────────────────────────────────────────────────────

    @staticmethod
    def cert_id_hash(certificate_id: str) -> bytes:
        """keccak256(certificate_id) — the on-chain mapping key."""
        from web3 import Web3

        return Web3.keccak(text=certificate_id)

    @staticmethod
    def _to_bytes32(hex_hash: str) -> bytes:
        raw = bytes.fromhex(hex_hash.removeprefix('0x'))
        if len(raw) != 32:
            raise BlockchainError(
                f'Expected a 32-byte hash, got {len(raw)} bytes from {hex_hash!r}.'
            )
        return raw

    # ─── Reads (free, no signer, no gas) ──────────────────────────────────────

    def get_certificate(self, certificate_id: str) -> OnChainCertificate:
        """Read a record. Used by public verification (FR-5.3)."""
        try:
            record = self.contract.functions.getCertificate(
                self.cert_id_hash(certificate_id)
            ).call()
        except BlockchainNotConfigured:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BlockchainError(f'getCertificate failed: {exc}') from exc

        cert_hash, issuer, issued_at, revoked = record
        zero_address = '0x' + '0' * 40

        return OnChainCertificate(
            cert_hash='0x' + cert_hash.hex().removeprefix('0x'),
            issuer=issuer,
            issued_at=int(issued_at),
            revoked=bool(revoked),
            exists=issuer.lower() != zero_address,
        )

    def is_authorized_issuer(self, address: str | None = None) -> bool:
        from web3 import Web3

        target = address or self.issuer_address
        return bool(
            self.contract.functions.authorizedIssuers(
                Web3.to_checksum_address(target)
            ).call()
        )

    # ─── Writes (signed, cost gas, serialised) ────────────────────────────────

    def issue_certificate(self, certificate_id: str, certificate_hash: str) -> TxResult:
        """Anchor a certificate hash on-chain (FR-2.5)."""
        return self._send(
            self.contract.functions.issueCertificate(
                self.cert_id_hash(certificate_id),
                self._to_bytes32(certificate_hash),
            ),
            gas_limit=200_000,
            label=f'issueCertificate({certificate_id})',
        )

    def revoke_certificate(self, certificate_id: str) -> TxResult:
        """Flag a certificate revoked on-chain (FR-3.4)."""
        return self._send(
            self.contract.functions.revokeCertificate(
                self.cert_id_hash(certificate_id)
            ),
            gas_limit=120_000,
            label=f'revokeCertificate({certificate_id})',
        )

    def _send(self, fn, *, gas_limit: int, label: str) -> TxResult:
        timeout = getattr(settings, 'BLOCKCHAIN_TX_TIMEOUT', 180)

        with _nonce_lock:
            try:
                nonce = self.w3.eth.get_transaction_count(
                    self.account.address, 'pending'
                )
                tx = fn.build_transaction({
                    'from': self.account.address,
                    'nonce': nonce,
                    'gas': gas_limit,
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': self.w3.eth.chain_id,
                })
                signed = self.account.sign_transaction(tx)
                # web3 v6 renamed rawTransaction → raw_transaction in 6.13.
                raw = getattr(signed, 'raw_transaction', None) or signed.rawTransaction
                tx_hash = self.w3.eth.send_raw_transaction(raw)
            except BlockchainNotConfigured:
                raise
            except Exception as exc:  # noqa: BLE001
                raise BlockchainError(f'{label} failed to send: {exc}') from exc

        logger.info('%s submitted: %s', label, tx_hash.hex())

        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise BlockchainError(
                f'{label} sent as {tx_hash.hex()} but no receipt within {timeout}s: {exc}'
            ) from exc

        if receipt.status != 1:
            raise BlockchainError(f'{label} reverted on-chain (tx {tx_hash.hex()}).')

        return TxResult(
            tx_hash=_hex(tx_hash),
            block_number=int(receipt.blockNumber),
            gas_used=int(receipt.gasUsed),
        )

    # ─── Presentation ─────────────────────────────────────────────────────────

    @staticmethod
    def explorer_tx_url(tx_hash: str) -> str:
        """Public block-explorer link shown on the verification page (FR-5.5)."""
        base = getattr(
            settings, 'BLOCKCHAIN_EXPLORER_URL', 'https://amoy.polygonscan.com'
        ).rstrip('/')
        return f'{base}/tx/{tx_hash}'


def _hex(value) -> str:
    """Normalise a HexBytes/bytes tx hash to a single 0x-prefixed string."""
    raw = value.hex() if hasattr(value, 'hex') else str(value)
    return raw if raw.startswith('0x') else '0x' + raw


def get_service() -> BlockchainService:
    """Factory used by tasks and views so tests can patch a single symbol."""
    return BlockchainService()
