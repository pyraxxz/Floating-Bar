"""Explicit, fail-closed verification contracts for supported adapters.

The verification implementation remains content-free: targets may observe
structural control identity and value length, but never retain or compare the
submitted text. Each supported adapter gets its own contract key so a future
app-specific verification refinement cannot accidentally broaden another
application's evidence rules.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VerificationContract:
    mode: str
    family: str
    adapter_keys: frozenset[str]
    target_mode: str
    submit_mode: str
    proof_kind: str = "input-acceptance"
    allows_verified: bool = True


# Every concrete adapter has an explicit contract. The families describe the
# current shared implementation; the adapter-key binding is deliberately
# specific so per-app semantics can diverge without widening evidence.
_CONTRACTS = (
    VerificationContract(
        mode="telegram-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"telegram"}),
        target_mode="telegram-compose",
        submit_mode="telegram-send",
    ),
    VerificationContract(
        mode="whatsapp-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"whatsapp"}),
        target_mode="chat-structured-focus",
        submit_mode="enter",
    ),
    VerificationContract(
        mode="discord-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"discord"}),
        target_mode="chat-structured-focus",
        submit_mode="enter",
    ),
    VerificationContract(
        mode="slack-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"slack"}),
        target_mode="chat-structured-focus",
        submit_mode="enter",
    ),
    VerificationContract(
        mode="teams-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"teams"}),
        target_mode="chat-structured-focus",
        submit_mode="enter",
    ),
    VerificationContract(
        mode="terminal-input-clear",
        family="terminal-input-clear",
        adapter_keys=frozenset({"terminal", "cmd", "powershell"}),
        target_mode="terminal-structured-focus",
        submit_mode="enter",
    ),
)

_BY_MODE = {contract.mode: contract for contract in _CONTRACTS}
_SUPPORTED_PROOF_KINDS = frozenset({"input-acceptance", "semantic-delivery", "semantic-execution"})

# Backward-compatible family aliases used by older callers/tests. They are
# intentionally not adapter-registry modes and never identify a concrete app.
_LEGACY_FAMILY_MODES = {
    "compose-clear": "chat-compose-clear",
}


def verification_contract(spec) -> Optional[VerificationContract]:
    """Return the exact contract for an adapter, or None when unsupported."""
    if spec is None:
        return None
    mode = str(getattr(spec, "verification_mode", "") or "")
    key = str(getattr(spec, "key", "") or "")
    contract = _BY_MODE.get(mode)
    if contract is None:
        family = _LEGACY_FAMILY_MODES.get(mode)
        if family:
            for candidate in _CONTRACTS:
                if candidate.family == family and key in candidate.adapter_keys:
                    return candidate
        return None
    return contract if key in contract.adapter_keys else None


def registry_validation_errors(adapter_specs) -> tuple[str, ...]:
    """Validate verified adapters against their exact routing contract."""
    errors: list[str] = []
    for spec in adapter_specs:
        mode = str(getattr(spec, "verification_mode", "unverified") or "unverified")
        key = str(getattr(spec, "key", "") or "")
        if mode in {"unverified", "none"}:
            continue
        contract = _BY_MODE.get(mode)
        if contract is None:
            if mode in _LEGACY_FAMILY_MODES:
                continue
            errors.append(f"missing verification contract: {key}/{mode}")
            continue
        if key not in contract.adapter_keys:
            errors.append(f"verification contract mismatch: {key}/{mode}")
            continue
        actual_target_mode = str(getattr(spec, "target_mode", "") or "")
        actual_submit_mode = str(getattr(spec, "submit_mode", "") or "")
        if contract.proof_kind not in _SUPPORTED_PROOF_KINDS:
            errors.append(
                f"unsupported verification proof kind: {key}/{contract.proof_kind}"
            )
        if actual_target_mode != contract.target_mode:
            errors.append(
                f"verification target contract mismatch: {key}/{actual_target_mode}"
            )
        if actual_submit_mode != contract.submit_mode:
            errors.append(
                f"verification submit contract mismatch: {key}/{actual_submit_mode}"
            )
    return tuple(errors)


def verification_proof_kind(spec) -> Optional[str]:
    """Return the exact proof scope authorized by the adapter contract."""
    contract = verification_contract(spec)
    if contract is None:
        return None
    return contract.proof_kind


def is_chat_compose_verification(spec) -> bool:
    """Return True only for a concrete chat compose verification contract."""
    contract = verification_contract(spec)
    if contract is None or contract.family != "chat-compose-clear":
        return False
    return (
        str(getattr(spec, "target_mode", "") or "") == contract.target_mode
        and str(getattr(spec, "submit_mode", "") or "") == contract.submit_mode
    )


def is_terminal_input_verification(spec) -> bool:
    """Return True only for the explicit terminal input-clear contract."""
    contract = verification_contract(spec)
    if contract is None or contract.family != "terminal-input-clear":
        return False
    return (
        str(getattr(spec, "target_mode", "") or "") == contract.target_mode
        and str(getattr(spec, "submit_mode", "") or "") == contract.submit_mode
    )


__all__ = [
    "VerificationContract",
    "is_chat_compose_verification",
    "is_terminal_input_verification",
    "verification_proof_kind",
    "registry_validation_errors",
    "verification_contract",
]
