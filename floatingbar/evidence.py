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

    @property
    def state(self):
        """Compatibility view for older result consumers."""
        return self


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


def from_result(strategy: Optional[str], error: Optional[str] = None) -> SubmissionEvidence:
    """Convert a legacy injector result into structured evidence."""
    if error:
        return SubmissionEvidence(
            EvidenceState.FAILED,
            strategy=strategy,
            detail=error,
            retryable=True,
        )
    if not strategy:
        return SubmissionEvidence(EvidenceState.UNKNOWN, retryable=False)

    normalized = strategy.lower()
    # Check the longer/negative forms first: "unverified" contains the
    # substring "verified", so the broad positive check must come last.
    if "verification-unavailable" in normalized:
        return SubmissionEvidence(
            EvidenceState.UNAVAILABLE,
            strategy=strategy,
            retryable=False,
        )
    if "unverified" in normalized:
        return SubmissionEvidence(
            EvidenceState.SUBMITTED,
            strategy=strategy,
            retryable=False,
        )
    if "verified" in normalized:
        return SubmissionEvidence(
            EvidenceState.VERIFIED,
            strategy=strategy,
            retryable=False,
        )
    # A concrete strategy that returned without verification still means an
    # action was attempted, so classify it as submitted-but-uncertain.
    return SubmissionEvidence(
        EvidenceState.SUBMITTED,
        strategy=strategy,
        retryable=False,
    )
