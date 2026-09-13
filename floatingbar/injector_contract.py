"""Structural contract for background text injectors.

The contract deliberately stays smaller than any concrete injector. It captures
only the operation the transaction executor needs, so Telegram's current
hardening layers and future application adapters can share the same boundary.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class BackgroundInjector(Protocol):
    """Minimal capability required to execute one prepared send."""

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        """Inject text into the already-selected background target."""


__all__ = ["BackgroundInjector"]
