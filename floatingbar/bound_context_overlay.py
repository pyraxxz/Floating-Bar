"""Production overlay that enforces immutable Telegram target binding."""

from .bound_target import BoundTelegramTarget
from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .transaction import SendCompletion


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Context-aware overlay with an exact target lease per send attempt."""

    def __init__(self):
        super().__init__()
        self.target = BoundTelegramTarget(self.target)
        self.injector.target = self.target

    def _send_finished(self, completion: SendCompletion) -> None:
        try:
            super()._send_finished(completion)
        finally:
            # A transaction binding must never leak into the next attempt.
            self.target.release()
