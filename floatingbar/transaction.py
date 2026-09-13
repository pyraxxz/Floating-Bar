"""Immutable data for one background-send transaction.

The UI and worker are intentionally separated: a send request captures the
user's text and restoration target before the background thread starts; a
prepared send attempt then adds the exact Telegram target lease and context;
the completion result carries the same attempt id back to the UI.
"""

from dataclasses import dataclass
from typing import Iterator, NamedTuple, Optional, Tuple

from .evidence import EvidenceState, from_result


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
        object.__setattr__(obj, "_immutable", True)
        return obj

    def __setattr__(self, name, value):
        if getattr(self, "_immutable", False):
            raise AttributeError("SendCandidate is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise AttributeError("SendCandidate is immutable")

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
class SendRequest:
    """Immutable user send request handed to the background worker."""

    attempt_id: int
    text: str
    restore_hwnd: int = 0

    @property
    def valid(self) -> bool:
        return bool(
            isinstance(self.attempt_id, int) and
            not isinstance(self.attempt_id, bool) and
            self.attempt_id > 0 and
            isinstance(self.text, str) and
            bool(self.text.strip()) and
            isinstance(self.restore_hwnd, int) and
            not isinstance(self.restore_hwnd, bool) and
            self.restore_hwnd >= 0
        )


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
            isinstance(self.attempt_id, int) and
            not isinstance(self.attempt_id, bool) and
            self.attempt_id > 0 and
            isinstance(self.text, str) and
            bool(self.text.strip()) and
            isinstance(self.target, TargetScope) and
            self.target.valid
        )


@dataclass(frozen=True)
class SendCompletion:
    """Immutable result crossing the background-worker/UI boundary.

    The iterator is a temporary compatibility bridge for legacy UI consumers.
    New producers should enqueue the object itself rather than a loosely typed
    tuple.
    """

    attempt_id: int
    strategy: Optional[str] = None
    error: Optional[str] = None
    evidence_state: Optional[EvidenceState] = None

    @classmethod
    def from_result(
        cls,
        attempt_id: int,
        strategy: Optional[str] = None,
        error: Optional[str] = None,
    ) -> "SendCompletion":
        evidence = from_result(strategy, error)
        return cls(
            attempt_id=attempt_id,
            strategy=strategy,
            error=error,
            evidence_state=evidence.state,
        )

    def __iter__(self) -> Iterator[object]:
        """Expose the legacy three-value view while callers migrate."""
        yield self.attempt_id
        yield self.strategy
        yield self.error

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
    "SendRequest",
    "SendAttempt",
    "SendCompletion",
]
