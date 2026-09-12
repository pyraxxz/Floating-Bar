"""Typed submission evidence shared by the injector and UI layers."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EvidenceState(str, Enum):
    """What the injector can honestly claim about a send attempt."""

    FAILED = "failed"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    UNAVAILABLE = "verification-unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SubmissionEvidence:
    """Structured result for one send attempt.

    `strategy` is retained for diagnostics/backwards compatibility; callers
    should branch on `state` and `retryable` instead of parsing it.
    """

    state: EvidenceState
    strategy: Optional[str] = None
    detail: Optional[str] = None
    retryable: bool = False

    @property
    def confirmed(self) -> bool:
        return self.state is EvidenceState.VERIFIED

    @property
    def uncertain(self) -> bool:
        return self.state in (
            EvidenceState.SUBMITTED,
            EvidenceState.UNAVAILABLE,
            EvidenceState.UNKNOWN,
        )
