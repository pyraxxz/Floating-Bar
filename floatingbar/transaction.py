"""Immutable data for one background-send transaction.

The UI and worker are intentionally separated: a send attempt captures its
identity and target before the background thread starts, while the completion
result carries the same attempt id back to the UI. This makes stale-worker
results and accidental target changes explicit data rather than a collection
of loosely related mutable fields.
"""

from dataclasses import dataclass
from typing import NamedTuple, Optional

from .evidence import EvidenceState


class TargetScope(NamedTuple):
    """Immutable HWND/PID pair that remains compatible with tuple callers."""

    hwnd: int
    pid: int

    @property
    def valid(self) -> bool:
        return bool(self.hwnd and self.pid)


@dataclass(frozen=True)
class SendAttempt:
    attempt_id: int
    text: str
    target: TargetScope
    restore_hwnd: int = 0
    context: object = None

    @property
    def valid(self) -> bool:
        return bool(self.attempt_id > 0 and self.text and self.target.valid)


@dataclass(frozen=True)
class SendCompletion:
    attempt_id: int
    strategy: Optional[str] = None
    error: Optional[str] = None
    evidence_state: Optional[EvidenceState] = None

    @property
    def failed(self) -> bool:
        return self.error is not None


__all__ = ["TargetScope", "SendAttempt", "SendCompletion"]
