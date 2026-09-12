"""Production overlay wired to the scope-guarded recovery injector.

The existing overlay remains unchanged; this tiny subclass replaces only
its injector instance so the optional recovery strategies receive the same
Telegram target-scope guarantees as the invisible path.
"""

from .overlay import OrbRelayWindow as _BaseOrbRelayWindow
from .recovery import ScopeGuardedRecoveryInjector


class OrbRelayWindow(_BaseOrbRelayWindow):
    """Overlay using the scope-guarded recovery injector."""

    def __init__(self):
        super().__init__()
        self.injector = ScopeGuardedRecoveryInjector(self.target)
