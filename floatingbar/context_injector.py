"""Context-aware injector that adds non-content conversation guards.

The existing scope-guarded injector protects the Telegram top-level HWND/PID.
This layer adds a one-way fingerprint of the Telegram window title as an
additional signal. The raw title is never retained, logged, or persisted.
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
        self.window_context = context

    def _assert_window_context(self, stage: str) -> None:
        context = self.window_context
        if context is None:
            return
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

    def _land_text(self, box, hwnd: int, text: str):
        self._assert_window_context("before compose landing")
        result = super()._land_text(box, hwnd, text)
        self._assert_window_context("after compose landing")
        return result

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool, landing: str):
        self._assert_window_context("before invisible submission")
        result = super()._submit_invisible(box, hwnd, primary_ctrl, landing)
        self._assert_window_context("after invisible submission")
        return result

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool, restore_hwnd: int) -> bool:
        self._assert_window_context("before focus-steal recovery")
        result = super()._submit_focus_steal(box, hwnd, primary_ctrl, restore_hwnd)
        self._assert_window_context("after focus-steal recovery")
        return result

    def _strategy_b(self, box, text: str, primary_ctrl: bool, restore_hwnd: int) -> bool:
        self._assert_window_context("before clipboard recovery")
        result = super()._strategy_b(box, text, primary_ctrl, restore_hwnd)
        self._assert_window_context("after clipboard recovery")
        return result
