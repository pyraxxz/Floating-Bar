"""Compatibility entry point for the production context-aware overlay.

Target binding and completion lifecycle are already owned by
``context_overlay.OrbRelayWindow``. This module intentionally stays as a
thin import-compatible subclass so the executable entry point does not need
to change while avoiding a second BoundTelegramTarget wrapper around the
coordinator's lease.
"""

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay; target binding is owned by the parent class."""

    pass


__all__ = ["OrbRelayWindow"]
