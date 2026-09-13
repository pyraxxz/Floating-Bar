"""Production overlay that enforces immutable Telegram target binding."""

from .bound_target import BoundTelegramTarget
from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Context-aware overlay with an exact target lease per send attempt."""

    def __init__(self):
        super().__init__()
        self.target = BoundTelegramTarget(self.target)
        self.injector.target = self.target

    def _send_finished(self, attempt_id: int, strategy: str, error) -> None:
        try:
            super()._send_finished(attempt_id, strategy, error)
        finally:
            # A transaction binding must never leak into the next attempt.
            self.target.release()
