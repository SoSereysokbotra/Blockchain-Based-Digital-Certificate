"""Recording every chain interaction, successful or not (FR-2.10)."""
from __future__ import annotations

import time
from contextlib import contextmanager

from .models import BlockchainInteractionLog, InteractionType


@contextmanager
def record_interaction(interaction_type: str, certificate=None, certificate_id: str = ''):
    """
    Log one attempt, whatever the outcome.

    A context manager rather than a decorator so the caller can attach the
    transaction hash to the same row it will be judged by. The `finally` block
    is what makes FR-2.10 hold: a failing attempt writes its row on the way out
    of the exception, so a FAILED certificate always has a matching log entry
    explaining why.
    """
    started = time.monotonic()
    entry = {'tx_hash': '', 'block_number': None, 'gas_used': None}
    error = None

    try:
        yield entry
    except Exception as exc:  # noqa: BLE001 — re-raised below
        error = exc
        raise
    finally:
        BlockchainInteractionLog.objects.create(
            certificate=certificate,
            certificate_public_id=(
                certificate_id or (certificate.certificate_id if certificate else '')
            ),
            interaction_type=interaction_type,
            succeeded=error is None,
            tx_hash=entry.get('tx_hash') or '',
            block_number=entry.get('block_number'),
            gas_used=entry.get('gas_used'),
            error_message=str(error)[:2000] if error else '',
            duration_ms=int((time.monotonic() - started) * 1000),
        )


__all__ = ['record_interaction', 'InteractionType', 'BlockchainInteractionLog']
