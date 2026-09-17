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
    allows_verified: bool = True


# Every concrete adapter has an explicit contract. The families describe the
# current shared implementation; the adapter-key binding is deliberately
# specific so per-app semantics can diverge without widening evidence.
_CONTRACTS = (
    VerificationContract(
        mode="telegram-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"telegram"}),
    ),
    VerificationContract(
        mode="whatsapp-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"whatsapp"}),
    ),
    VerificationContract(
        mode="discord-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"discord"}),
    ),
    VerificationContract(
        mode="slack-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"slack"}),
    ),
    VerificationContract(
        mode="teams-compose-clear",
        family="chat-compose-clear",
        adapter_keys=frozenset({"teams"}),
    ),
    VerificationContract(
        mode="terminal-input-clear",
        family="terminal-input-clear",
        adapter_keys=frozenset({"terminal", "cmd", "powershell"}),
    ),
)

_BY_MODE = {contract.mode: contract for contract in _CONTRACTS}

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
            # Legacy mode remains usable only for known app keys that belong
            # to the same family. This preserves compatibility without letting
            # an arbitrary adapter claim a concrete app contract.
            for candidate in _CONTRACTS:
                if candidate.family == family and key in candidate.adapter_keys:
                    return candidate
        return None
    return contract if key in contract.adapter_keys else None


def registry_validation_errors(adapter_specs) -> tuple[str, ...]:
    """Validate that every verified adapter is bound to one concrete contract."""
    errors: list[str] = []
    seen_modes: set[str] = set()
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
        if mode in seen_modes:
            errors.append(f"duplicate verification mode: {mode}")
        seen_modes.add(mode)
    return tuple(errors)


def is_chat_compose_verification(spec) -> bool:
    """Return True only for a concrete chat compose verification contract."""
    contract = verification_contract(spec)
    return bool(contract and contract.family == "chat-compose-clear")


def is_terminal_input_verification(spec) -> bool:
    """Return True only for the explicit terminal input-clear contract."""
    contract = verification_contract(spec)
    return bool(contract and contract.family == "terminal-input-clear")


__all__ = [
    "VerificationContract",
    "is_chat_compose_verification",
    "is_terminal_input_verification",
    "registry_validation_errors",
    "verification_contract",
]
