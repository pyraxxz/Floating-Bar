"""Explicit lifecycle for one immutable send transaction.

The transaction data objects describe *what* will be sent. This module
centralizes *where the attempt is in its lifecycle* so preflight, injection,
evidence, retry, and completion cannot silently drift into incompatible
states.
"""

from enum import Enum
from typing import FrozenSet, Mapping

from .evidence import EvidenceState


class TransactionState(str, Enum):
    """Stable phases visible across coordinator, worker, and UI layers."""

    IDLE = "idle"
    PREPARING = "preparing"
    READY = "ready"
    SENDING = "sending"
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    FAILED = "failed"
    REJECTED = "rejected"


# Only forward, semantically safe transitions are allowed. A finished attempt
# never re-enters preparation or sending; a new request must create a new id.
_ALLOWED: Mapping[TransactionState, FrozenSet[TransactionState]] = {
    TransactionState.IDLE: frozenset({TransactionState.PREPARING}),
    TransactionState.PREPARING: frozenset({
        TransactionState.READY,
        TransactionState.REJECTED,
    }),
    TransactionState.READY: frozenset({TransactionState.SENDING}),
    TransactionState.SENDING: frozenset({
        TransactionState.VERIFIED,
        TransactionState.UNCERTAIN,
        TransactionState.FAILED,
    }),
    TransactionState.VERIFIED: frozenset(),
    TransactionState.UNCERTAIN: frozenset(),
    TransactionState.FAILED: frozenset(),
    TransactionState.REJECTED: frozenset(),
}


class InvalidTransactionTransition(RuntimeError):
    """Raised when an attempt tries to skip or repeat a lifecycle phase."""


def allowed_transitions(state: TransactionState) -> FrozenSet[TransactionState]:
    """Return the immutable set of states reachable directly from ``state``."""
    return _ALLOWED[state]


class TransactionLifecycle:
    """Small attempt-scoped state machine with monotonic transition safety."""

    __slots__ = ("_attempt_id", "_state")

    def __init__(self, attempt_id: int):
        if not isinstance(attempt_id, int) or isinstance(attempt_id, bool) or attempt_id <= 0:
            raise ValueError("attempt_id must be a positive integer")
        self._attempt_id = attempt_id
        self._state = TransactionState.IDLE

    @property
    def attempt_id(self) -> int:
        return self._attempt_id

    @property
    def state(self) -> TransactionState:
        return self._state

    @property
    def terminal(self) -> bool:
        return self._state in {
            TransactionState.VERIFIED,
            TransactionState.UNCERTAIN,
            TransactionState.FAILED,
            TransactionState.REJECTED,
        }

    def transition(self, next_state: TransactionState) -> TransactionState:
        """Advance exactly one legal lifecycle edge and return the new state."""
        if next_state not in allowed_transitions(self._state):
            raise InvalidTransactionTransition(
                f"attempt {self._attempt_id}: {self._state.value} -> "
                f"{next_state.value} is not allowed"
            )
        self._state = next_state
        return self._state

    def begin_prepare(self) -> TransactionState:
        return self.transition(TransactionState.PREPARING)

    def mark_ready(self) -> TransactionState:
        return self.transition(TransactionState.READY)

    def begin_send(self) -> TransactionState:
        return self.transition(TransactionState.SENDING)

    def complete_verified(self) -> TransactionState:
        return self.transition(TransactionState.VERIFIED)

    def complete_uncertain(self) -> TransactionState:
        return self.transition(TransactionState.UNCERTAIN)

    def complete_failed(self) -> TransactionState:
        return self.transition(TransactionState.FAILED)

    def reject(self) -> TransactionState:
        return self.transition(TransactionState.REJECTED)

    def complete_from_evidence(self, evidence_state: EvidenceState) -> TransactionState:
        """Map one typed submission result to the only legal terminal state."""
        if not isinstance(evidence_state, EvidenceState):
            raise TypeError("evidence_state must be an EvidenceState")
        if evidence_state is EvidenceState.VERIFIED:
            return self.complete_verified()
        if evidence_state in (
            EvidenceState.SUBMITTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.UNKNOWN,
        ):
            return self.complete_uncertain()
        if evidence_state is EvidenceState.FAILED:
            return self.complete_failed()
        raise InvalidTransactionTransition(
            f"attempt {self._attempt_id}: unsupported evidence state "
            f"{evidence_state!r}"
        )


__all__ = [
    "InvalidTransactionTransition",
    "TransactionLifecycle",
    "TransactionState",
    "allowed_transitions",
]
