"""Production overlay with non-content Telegram conversation guards."""

import config

from . import trace
from . import winapi
from .bound_target import BoundTelegramTarget
from .context import capture
from .context_injector import ContextGuardedRecoveryInjector
from .injector import InjectionFailed
from .recovery_overlay import OrbRelayWindow as _RecoveryOrbRelayWindow
from .target import TelegramNotFound
from .transaction_coordinator import SendTransactionCoordinator, TransactionRejected


class OrbRelayWindow(_RecoveryOrbRelayWindow):
    """Recovery-aware overlay that also guards the selected Telegram context."""

    def __init__(self):
        super().__init__()
        self.target = BoundTelegramTarget(self.target)
        self.injector = ContextGuardedRecoveryInjector(self.target)
        self.coordinator = SendTransactionCoordinator(self.target)
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

    def _execute_prepared_attempt(self, text: str, restore_hwnd: int, attempt_id: int) -> None:
        """Run an already-prepared transaction without re-selecting its target.

        The coordinator has already converted the Telegram target into an
        immutable HWND/PID lease. The worker therefore receives only the
        transaction's restore HWND here; target selection is intentionally not
        repeated from the restore handle.
        """
        comtypes = None
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            comtypes = None

        strategy = None
        error = None
        try:
            strategy = self.injector.send(text, restore_hwnd=restore_hwnd)
        except (TelegramNotFound, InjectionFailed) as exc:
            error = str(exc)
        except Exception as exc:
            error = f"Unexpected error: {exc}"
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        self._result_q.put((attempt_id, strategy, error))

    def _send_worker(self, text: str, work_hwnd: int, attempt_id: int) -> None:
        # Keep the user's original foreground HWND separate from the Telegram
        # target. The latter is a lease target; the former is what recovery
        # should restore if a posted click or opt-in fallback raises Telegram.
        preferred = work_hwnd if self._is_telegram_window(work_hwnd) else 0
        try:
            prepared = self.coordinator.prepare(
                text=text,
                attempt_id=attempt_id,
                preferred_hwnd=preferred,
                restore_hwnd=work_hwnd,
            )
        except TransactionRejected as exc:
            trace.trace(f"transaction: preparation rejected safely: {exc}")
            self._result_q.put((attempt_id, None, str(exc)))
            return
        except Exception as exc:
            trace.trace(f"transaction: unexpected preparation failure: {exc}")
            self._result_q.put(
                (
                    attempt_id,
                    None,
                    f"Telegram send preflight failed safely: {exc}",
                )
            )
            return

        transaction = prepared.attempt
        self._active_transaction = transaction
        self._work_hwnd = transaction.target.hwnd
        self._attempt_context = transaction.context
        self.injector.set_window_context(transaction.context)
        self._execute_prepared_attempt(
            transaction.text,
            transaction.restore_hwnd,
            transaction.attempt_id,
        )

    def _send_finished(self, attempt_id: int, strategy: str, error) -> None:
        is_current = (
            attempt_id == getattr(self, "_active_attempt_id", 0)
        )
        context = self._active_transaction.context if (
            self._active_transaction is not None and
            self._active_transaction.attempt_id == attempt_id
        ) else self._attempt_context
        release = getattr(self.target, "release", None)
        try:
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
        finally:
            # A malformed completion handler must never strand the exact target
            # lease. Stale results still cannot release the lease belonging to
            # a newer active attempt.
            if is_current and callable(release):
                release()


__all__ = ["OrbRelayWindow"]
