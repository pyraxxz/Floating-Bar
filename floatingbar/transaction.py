"""Immutable data for one background-send transaction.

The UI and worker are intentionally separated: a send attempt captures its
identity and target before the background thread starts, while the completion
result carries the same attempt id back to the UI. This makes stale-worker
results and accidental target changes explicit data rather than a collection
of loosely related mutable fields.
"""

from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple

from .evidence import EvidenceState


class TargetScope(NamedTuple):
    """Immutable HWND/PID pair that remains compatible with tuple callers."""

    hwnd: int
    pid: int

    @property
    def valid(self) -> bool:
        return bool(self.hwnd and self.pid)


class SendCandidate(NamedTuple):
    """Safe Send-button evidence and client-relative click coordinates."""

    name: str
    client_x: int
    client_y: int
    evidence_score: float = 0.0


def candidate_parts(candidate) -> Tuple[str, int, int]:
    """Return name/x/y for a typed SendCandidate or legacy 3-tuple."""
    if isinstance(candidate, SendCandidate):
        return candidate.name, candidate.client_x, candidate.client_y
    return candidate[0], candidate[1], candidate[2]


@dataclass(frozen=True)
class SendAttempt:
    attempt_id: int
    text: str
    target: TargetScope
    restore_hwnd: int = 0
    context: object = None

    @property
    def valid(self) -> bool:
        return bool(
            self.attempt_id > 0 and
            bool(self.text.strip()) and
            self.target.valid
        )


@dataclass(frozen=True)
class SendCompletion:
    attempt_id: int
    strategy: Optional[str] = None
    error: Optional[str] = None
    evidence_state: Optional[EvidenceState] = None

    @property
    def failed(self) -> bool:
        return bool(
            self.error is not None or
            self.evidence_state is EvidenceState.FAILED
        )


__all__ = [
    "TargetScope",
    "SendCandidate",
    "candidate_parts",
    "SendAttempt",
    "SendCompletion",
]
