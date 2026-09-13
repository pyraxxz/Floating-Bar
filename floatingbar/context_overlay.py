"""Production overlay with non-content Telegram conversation guards."""

import config

from . import trace
from . import winapi
from .context import capture
from .context_injector import ContextGuardedRecoveryInjector
from .preflight import run as run_preflight
from .recovery_overlay import OrbRelayWindow as _RecoveryOrbRelayWindow
from .transaction import SendAttempt, TargetScope


class OrbRelayWindow(_RecoveryOrbRelayWindow):
    """Recovery-aware overlay that also guards the selected Telegram context."""

    def __init__(self):
        super().__init__()
        self.injector = ContextGuardedRecoveryInjector(self.target)
        self._attempt_context = None
        self._retry_context = None
        self._active_transaction = None

    @staticmethod
    def _is_telegram_window(hwnd: int) -> bool:
        if not hwnd:
            return False
        try:
            pid = winapi.get_window_pid(hwnd)
            image = winapi.get_process_image_name(pid)
            base = image.rsplit("\\", 1)[-1] if image else ""
            if base and config.PROCESS_NAME_RE.search(base):
                return True
            title = winapi.get_window_title(hwnd)
            return bool(title and config.TITLE_FALLBACK_RE.search(title))
        except Exception:
            return False

    def _capture_target_context(self, hwnd: int = 0) -> None:
        target_hwnd = hwnd or self.target.hwnd
        if target_hwnd and self._is_telegram_window(target_hwnd):
            self._attempt_context = capture(target_hwnd)
            self.injector.set_window_context(self._attempt_context)
            trace.trace("window context: captured non-content Telegram title context")

    def _expand(self) -> None:
        super()._expand()
        if self._state == "bar" and self._work_hwnd and self._is_telegram_window(self._work_hwnd):
            self._attempt_context = capture(self._work_hwnd)
            self.injector.set_window_context(self._attempt_context)
            trace.trace("window context: captured non-content Telegram title context")
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
                config.ERROR_COLOR,
            )
            self._set_retry_menu_enabled(True)
            self.injector.set_window_context(self._retry_context)
            return

        super()._retry_failed_draft()
        self._attempt_context = self._retry_context
        if self._attempt_context is None:
            self._capture_target_context()
        self.injector.set_window_context(self._attempt_context)

    def _on_key_typed(self, _event) -> None:
        was_retry_draft = self._retry_draft is not None
        super()._on_key_typed(_event)
        if was_retry_draft and self._retry_draft is None:
            self._retry_context = None
            self._attempt_context = None
            self.injector.set_window_context(None)
            trace.trace("window context: failed-draft retry converted to new compose attempt")

    def _on_enter_key(self, _event=None) -> str:
        self.injector.set_window_context(self._attempt_context)
        return super()._on_enter_key(_event)

    def _send_worker(self, text: str, work_hwnd: int, attempt_id: int) -> None:
        # First prove that the selected Telegram target is viable without any
        # click, keypress, focus change, or clipboard mutation. This turns the
        # diagnostics preflight into a production transaction gate.
        try:
            preferred = work_hwnd if self._is_telegram_window(work_hwnd) else 0
            preflight = run_preflight(self.target, preferred_hwnd=preferred)
            trace.trace(
                f"preflight: status={preflight.status} "
                f"path={preflight.submission_path} "
                f"context_guard={preflight.context_guard_available}"
            )
            if not preflight.ready:
                error = "; ".join(preflight.reasons) or "Telegram send preflight blocked the send."
                self._result_q.put((attempt_id, None, error))
                return

            # Bind the entire transaction to the exact preflight target. A
            # later Telegram rescan must not silently choose another window.
            work_hwnd = preflight.hwnd
            self._work_hwnd = work_hwnd
            if self._attempt_context is None or self._attempt_context.hwnd != work_hwnd:
                self._capture_target_context(work_hwnd)
            context = self._attempt_context
        except Exception as exc:
            trace.trace(f"preflight: unexpected failure: {exc}")
            self._result_q.put(
                (
                    attempt_id,
                    None,
                    f"Telegram send preflight failed safely: {exc}",
                )
            )
            return

        if context is None or context.hwnd != work_hwnd:
            trace.trace("window context: target identity could not be safely captured; aborting")
            self._result_q.put(
                (
                    attempt_id,
                    None,
                    "Telegram target identity could not be safely captured; the send was stopped.",
                )
            )
            return

        if not context.matches():
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

        transaction = SendAttempt(
            attempt_id=attempt_id,
            text=text,
            target=TargetScope(preflight.hwnd, preflight.pid),
            restore_hwnd=work_hwnd,
            context=context,
        )
        if not transaction.valid:
            trace.trace("transaction: invalid immutable send attempt; aborting")
            self._result_q.put(
                (
                    attempt_id,
                    None,
                    "The send transaction could not be safely bound to its target; the send was stopped.",
                )
            )
            return

        self._active_transaction = transaction
        self.injector.set_window_context(context)
        super()._send_worker(transaction.text, transaction.target.hwnd, transaction.attempt_id)

    def _send_finished(self, attempt_id: int, strategy: str, error) -> None:
        is_current = (
            attempt_id == getattr(self, "_active_attempt_id", 0)
        )
        context = self._active_transaction.context if (
            self._active_transaction is not None and
            self._active_transaction.attempt_id == attempt_id
        ) else self._attempt_context
        super()._send_finished(attempt_id, strategy, error)
        if not is_current:
            return
        if self._retry_draft and context is not None:
            self._retry_context = context
        elif not self._retry_draft:
            self._retry_context = None
            self._attempt_context = None
            self.injector.set_window_context(None)
        self._active_transaction = None
