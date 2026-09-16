from typing import Optional

from .app_adapters import AppAdapterSpec
from .chat_composer_target import ChatComposerTarget
from .generic_target import BackgroundTypingTarget
from .terminal_target import TerminalTypingTarget


_CHAT_TARGETS = {"whatsapp", "discord", "slack", "teams"}


def target_for_adapter(spec: Optional[AppAdapterSpec]):
    """Build the safest target implementation for an adapter capability."""
    if spec is None:
        return BackgroundTypingTarget()
    if spec.key == "terminal":
        return TerminalTypingTarget()
    if spec.key in _CHAT_TARGETS:
        return ChatComposerTarget()
    return BackgroundTypingTarget()


def target_mode_for(spec: Optional[AppAdapterSpec]) -> str:
    """Expose the selected target strategy without requiring a target object."""
    if spec is None:
        return "unsupported"
    return spec.target_mode


__all__ = ["target_for_adapter", "target_mode_for"]
