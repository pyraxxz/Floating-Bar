"""Production overlay with non-content Telegram conversation guards."""

from . import config as _unused_config
from . import trace
from . import winapi
from .context import capture, WindowContext
from .context_injector import ContextGuardedRecoveryInjector
from .recovery_overlay import OrbRelayWindow as _RecoveryOrbRelayWindow


class OrbRelayWindow(_RecoveryOrbRelayWindow):
    """Recovery-aware overlay that also guards the selected Telegram context."""

    def __init__(self):
        super().__init__()
        self.injector = ContextGuardedRecoveryInjector(self.target)
        self._attempt_context = None
        self._retry_context = None

    @staticmethod
    def _is_telegram_window(hwnd: int) -> bool:
        if not hwnd:
            return False
        try:
            pid = winapi.get_window_pid(hwnd)
            image = winapi.get_process_image_name(pid)
            base = image.rsplit("\\", 1)[-1] if image else ""
            if base and __import__("config").PROCESS_NAME_RE.search(base):
                return True
            title = winapi.get_window_title(hwnd)
            return bool(title and __import__("config").TITLE_FALLBACK_RE.search(title))
        except Exception:
            return False

    def _expand(self) -> None:
        super()._expand()
        if self._state == "bar" and self._work_hwnd and self._is_telegram_window(self._work_hwnd):
            self._attempt_context = capture(self._work_hwnd)
            self.injector.set_window_context(self._attempt_context)
            trace.trace("window context: captured non-content Telegram title fingerprint")
        else:
            self._attempt_context = None
            self.injector.set_window_context(None)

    def _retry_failed_draft(self) -> None:
        if self._sending or not self._retry_draft:
            return

        if self._retry_context is not None and not self._retry_context.matches():
            self._show_bar()
            self._show_feedback(
                "The original Telegram chat/window changed. Return to it before retrying.",
                __import__("config").ERROR_COLOR,
            )
            self._set_retry_menu_enabled(True)
            self.injector.set_window_context(self._retry_context)
            return

        super()._retry_failed_draft()
        self._attempt_context = self._retry_context
        self.injector.set_window_context(self._attempt_context)

    def _on_enter_key(self, _event=None) -> str:
        self.injector.set_window_context(self._attempt_context)
        return super()._on_enter_key(_event)

    def _send_worker(self, text: str, work_hwnd: int, attempt_id: int) -> None:
        context = self._attempt_context
        if context is not None and not context.matches():
            trace.trace("window context: changed before send worker started; aborting")
            self._result_q.put(
                (
                    attempt_id,
                    None,
                    "The Telegram conversation or target window changed while the message was being prepared. "
                    "The send was stopped safely; return to the intended chat and try again.",
                )
            )
            return
        self.injector.set_window_context(context)
        super()._send_worker(text, work_hwnd, attempt_id)

    def _send_finished(self, attempt_id: int, strategy: str, error) -> None:
        is_current = attempt_id == getattr(self, "_active_attempt_id", 0)
        context = self._attempt_context
        super()._send_finished(attempt_id, strategy, error)
        if not is_current:
            return
        if self._retry_draft and context is not None:
            self._retry_context = context
        elif not self._retry_draft:
            self._retry_context = None
            self._attempt_context = None
            self.injector.set_window_context(None)
