"""Context-aware injector that adds non-content conversation guards.

The existing scope-guarded injector protects the Telegram top-level HWND/PID.
This layer adds a one-way fingerprint of the Telegram window title and other
non-content structural anchors as additional signals. Raw titles are never
retained, logged, or persisted.
"""

from .context import WindowContext
from .recovery import ScopeGuardedRecoveryInjector
from .injector import InjectionFailed
from . import trace


class ContextGuardedRecoveryInjector(ScopeGuardedRecoveryInjector):
    """Scope-guarded injector that also protects the selected window context."""

    def __init__(self, target):
        super().__init__(target)
        self.window_context = None

    def set_window_context(self, context: WindowContext = None) -> None:
        """Install only a real immutable WindowContext; reject malformed state."""
        if context is not None and not isinstance(context, WindowContext):
            trace.trace("window context: rejecting malformed context state")
            self.window_context = None
            return
        self.window_context = context

    def _assert_window_context(self, stage: str) -> None:
        context = self.window_context
        if context is None:
            return
        if not isinstance(context, WindowContext):
            trace.trace(f"window context malformed at {stage}; aborting")
            raise InjectionFailed(
                "Telegram conversation context became invalid; "
                "the send was stopped safely."
            )
        if not context.matches():
            trace.trace(
                f"window context mismatch at {stage}; "
                f"aborting without continuing"
            )
            raise InjectionFailed(
                "The Telegram conversation or target window changed while "
                "the message was being prepared. The send was stopped safely; "
                "return to the intended chat and try again."
            )

    def _assert_target_scope(self, hwnd: int, stage: str) -> None:
        """Extend the existing per-action HWND/PID guard with context."""
        super()._assert_target_scope(hwnd, stage)
        self._assert_window_context(stage)

    def _land_text(self, box, hwnd: int, text: str):
        self._assert_window_context("before compose landing")
        return super()._land_text(box, hwnd, text)
