"""Conservative evidence mapping for application-specific send adapters.

The adapter registry declares the strongest verification contract an app path
is currently allowed to claim. A generic path that only posts input can never
upgrade itself to VERIFIED merely because a lower layer returns a success-like
string; the registry remains the authority for what the adapter can prove.
"""

from . import trace
from .app_verification import is_chat_compose_verification, is_terminal_input_verification
from .evidence import EvidenceState, SubmissionEvidence, from_result


_VERIFIED_MODES = frozenset(
    {
        "compose-clear",
        "telegram-compose-clear",
        "whatsapp-compose-clear",
        "discord-compose-clear",
        "slack-compose-clear",
        "teams-compose-clear",
        "terminal-input-clear",
    }
)

_VERIFICATION_ALLOWLIST = {
    **{mode: frozenset({EvidenceState.VERIFIED}) for mode in _VERIFIED_MODES},
    "unverified": frozenset({EvidenceState.SUBMITTED}),
    "none": frozenset({EvidenceState.SUBMITTED}),
}


def _exact_verified_contract(spec) -> bool:
    """Return whether the live adapter is bound to a verified target contract."""
    return is_chat_compose_verification(spec) or is_terminal_input_verification(spec)


def evidence_for_adapter(
    spec,
    strategy: str | None = None,
    error: str | None = None,
    submission_evidence: SubmissionEvidence | None = None,
) -> SubmissionEvidence:
    """Return evidence bounded by the adapter's declared verification contract.

    ``submission_evidence`` is the preferred production path. Legacy strategy
    parsing remains available for compatibility, but callers that have a
    structured producer result do not need to recover evidence from text.
    """
    if error:
        raw = from_result(strategy, error)
    elif isinstance(submission_evidence, SubmissionEvidence):
        raw = submission_evidence
    else:
        raw = from_result(strategy, error)

    if raw.state is EvidenceState.BLOCKED or raw.state is EvidenceState.FAILED:
        result = raw
    else:
        mode = getattr(spec, "verification_mode", "unverified") if spec is not None else "unverified"
        allowed = _VERIFICATION_ALLOWLIST.get(mode, frozenset({EvidenceState.SUBMITTED}))

        if raw.state is EvidenceState.VERIFIED and not _exact_verified_contract(spec):
            allowed = frozenset({EvidenceState.SUBMITTED})

        if raw.state in allowed:
            result = raw
        else:
            # Unknown or unsupported verification modes fail closed to
            # submitted-but-unverified rather than allowing an accidental
            # VERIFIED result. Preserve trusted producer metadata so the
            # adapter cannot silently erase why the producer downgraded it.
            result = SubmissionEvidence(
                state=EvidenceState.SUBMITTED,
                strategy=raw.strategy or strategy,
                detail=raw.detail or "adapter verification contract does not prove submission",
                retryable=False,
            )

    spec_key = getattr(spec, "key", "legacy") if spec is not None else "legacy"
    trace.trace(
        f"stage=verification adapter={spec_key} state={result.state.value} "
        f"confirmed={'yes' if result.confirmed else 'no'}"
    )
    return result


__all__ = ["evidence_for_adapter"]
