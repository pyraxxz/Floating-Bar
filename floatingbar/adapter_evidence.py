"""Conservative evidence mapping for application-specific send adapters.

The adapter registry declares the strongest verification contract an app path
is currently allowed to claim. A generic path that only posts input can never
upgrade itself to VERIFIED merely because a lower layer returns a success-like
string; the registry remains the authority for what the adapter can prove.
"""

from .evidence import EvidenceState, SubmissionEvidence, from_result


_VERIFICATION_ALLOWLIST = {
    "compose-clear": frozenset({EvidenceState.VERIFIED}),
    "unverified": frozenset({EvidenceState.SUBMITTED}),
    "none": frozenset({EvidenceState.SUBMITTED}),
}


def evidence_for_adapter(spec, strategy: str | None = None, error: str | None = None) -> SubmissionEvidence:
    """Return evidence bounded by the adapter's declared verification contract."""
    raw = from_result(strategy, error)
    if error:
        return raw

    mode = getattr(spec, "verification_mode", "unverified") if spec is not None else "unverified"
    allowed = _VERIFICATION_ALLOWLIST.get(mode, frozenset({EvidenceState.SUBMITTED}))

    if raw.state in allowed:
        return raw
    if raw.state is EvidenceState.FAILED:
        return raw

    # Unknown or unsupported verification modes fail closed to submitted-but-
    # unverified rather than allowing an accidental VERIFIED result.
    return SubmissionEvidence(
        state=EvidenceState.SUBMITTED,
        strategy=strategy,
        detail="adapter verification contract does not prove submission",
        retryable=False,
    )


__all__ = ["evidence_for_adapter"]
