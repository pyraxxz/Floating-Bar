from typing import Optional

from .app_adapters import AppAdapterSpec
from .generic_target import BackgroundTypingTarget
from .terminal_target import TerminalTypingTarget


def target_for_adapter(spec: Optional[AppAdapterSpec]):
    """Build the safest target implementation for an adapter capability."""
    if spec is not None and spec.key == "terminal":
        return TerminalTypingTarget()
    return BackgroundTypingTarget()


def target_mode_for(spec: Optional[AppAdapterSpec]) -> str:
    """Expose the selected target strategy without requiring a target object."""
    if spec is None:
        return "unsupported"
    return spec.target_mode


__all__ = ["target_for_adapter", "target_mode_for"]
