"""Small contract for background-app targets.

This is intentionally structural rather than a framework. Telegram remains
implemented by the existing :class:`TelegramTarget`; the contract only names
the operations a future generic injector will need once the Telegram path is
proven stable in real-world use.
"""

from typing import Protocol

from .transaction import TargetScope


class BackgroundTarget(Protocol):
    """Minimum discovery contract shared by future app adapters."""

    def select_for_send(self, preferred_hwnd: int = 0) -> int:
        """Return the top-level window selected for this send attempt."""

    def scope(self) -> TargetScope:
        """Return the currently selected top-level HWND/PID scope."""

    def is_available(self) -> bool:
        """Return whether a usable target is currently discoverable."""


__all__ = ["BackgroundTarget"]
