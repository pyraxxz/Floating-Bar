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


class SendCandidate(tuple):
    """Three-value tuple-compatible Send evidence with a read-only score.

    The tuple payload deliberately remains `(name, client_x, client_y)` so
    older injector paths that unpack or slice candidates keep working. The
    evidence score is auxiliary metadata exposed as an attribute.
    """

    def __new__(cls, name: str, client_x: int, client_y: int,
                evidence_score: float = 0.0):
        obj = super().__new__(cls, (name, client_x, client_y))
        object.__setattr__(obj, "evidence_score", float(evidence_score))
        return obj

    def __setattr__(self, name, value):
        if name == "evidence_score" and hasattr(self, "evidence_score"):
            raise AttributeError("SendCandidate is immutable")
        object.__setattr__(self, name, value)

    @property
    def name(self) -> str:
        return self[0]

    @property
    def client_x(self) -> int:
        return self[1]

    @property
    def client_y(self) -> int:
        return self[2]


def candidate_parts(candidate) -> Tuple[str, int, int]:
    """Return name/x/y for a SendCandidate or legacy 3/4-value tuple."""
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
