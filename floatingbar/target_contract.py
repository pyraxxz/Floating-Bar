"""Small structural contract for background-app targets.

The contract intentionally names only the operations shared by every
background target at transaction-binding time. Application-specific discovery,
compose selection, evidence, and verification remain target-owned so the
generic transaction coordinator cannot accidentally depend on Telegram or
another adapter's UI model.
"""

from typing import Protocol, runtime_checkable

from .transaction import TargetScope


@runtime_checkable
class BackgroundTarget(Protocol):
    """Minimum transaction-binding contract for a background target."""

    def select_for_send(self, preferred_hwnd: int = 0) -> int:
        """Return the top-level window selected for this send attempt."""

    def scope(self) -> TargetScope:
        """Return the currently selected immutable HWND/PID scope."""

    def is_available(self) -> bool:
        """Return whether a usable target is currently discoverable."""

    def release(self) -> None:
        """Release any active transaction binding without retargeting."""


__all__ = ["BackgroundTarget"]
