"""Production overlay with non-content Telegram conversation guards."""

import config
import queue

from . import trace
from . import winapi
from .bound_target import BoundTelegramTarget
from .context import capture
from .context_injector import ContextGuardedRecoveryInjector
from .injector import InjectionFailed
from .recovery_overlay import OrbRelayWindow as _RecoveryOrbRelayWindow
from .target import TelegramNotFound
from .transaction import SendCompletion, SendRequest
from .transaction_coordinator import SendTransactionCoordinator, TransactionRejected
from .transaction_state import TransactionLifecycle, TransactionState
from .evidence import EvidenceState


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
        self._active_lifecycle = None

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
        retry_context = self._retry_context if self._retry_draft else None
        super()._expand()
        if self._state != "bar":
            return

        if self._retry_draft and retry_context is not None:
            self._attempt_context = retry_context
            self._work_hwnd = self._retry_target_hwnd or retry_context.hwnd
            self.injector.set_window_context(retry_context)
            trace.trace(
                "window context: preserving original failed-draft target on orb open"
            )
            return

        if self._work_hwnd and self._is_telegram_window(self._work_hwnd):
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

    def _queue_completion(
        self,
        attempt_id: int,
        strategy: str = None,
        error: str = None,
    ) -> None:
        """Queue one typed result across the worker/UI thread boundary."""
        self._result_q.put(
            SendCompletion.from_result(
                attempt_id=attempt_id,
                strategy=strategy,
                error=error,
            )
        )

    def _execute_prepared_attempt(self, text: str, restore_hwnd: int, attempt_id: int) -> None:
        """Run an already-prepared transaction without re-selecting its target."""
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
        except TelegramNotFound as exc:
            trace.trace_exception("worker Telegram target unavailable", exc)
            error = "Telegram is unavailable or its target could not be inspected safely."
        except InjectionFailed as exc:
            trace.trace_exception("worker Telegram injection failed", exc)
            error = "Telegram could not safely submit the message."
        except Exception as exc:
            trace.trace_exception("worker unexpected send failure", exc)
            error = "Telegram send failed safely due to an unexpected internal error."
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        self._queue_completion(attempt_id, strategy, error)

    def _send_worker_request(self, request: SendRequest) -> None:
        """Prepare and execute one immutable user request on the worker thread."""
        if not isinstance(request, SendRequest) or not request.valid:
            attempt_id = getattr(request, "attempt_id", 0)
            self._queue_completion(
                attempt_id,
                None,
                "The send request was invalid and was stopped safely.",
            )
            return

        lifecycle = TransactionLifecycle(request.attempt_id)
        lifecycle.begin_prepare()
        self._active_lifecycle = lifecycle
        trace.trace("stage=adapter key=telegram")

        work_hwnd = request.restore_hwnd
        preferred = work_hwnd if self._is_telegram_window(work_hwnd) else 0
        try:
            prepared = self.coordinator.prepare_request(
                request,
                preferred_hwnd=preferred,
            )
        except TransactionRejected as exc:
            lifecycle.block()
            trace.trace(
                "transaction: preparation blocked safely; "
                f"state={lifecycle.state.value}"
            )
            self._queue_completion(request.attempt_id, "preflight (blocked)")
            return
        except Exception as exc:
            lifecycle.reject()
            trace.trace_exception(
                f"transaction: unexpected preparation failure; state={lifecycle.state.value}",
                exc,
            )
            self._queue_completion(
                request.attempt_id,
                None,
                "Telegram send preflight failed safely.",
            )
            return

        lifecycle.mark_ready()
        transaction = prepared.attempt
        self._active_transaction = transaction
        self._work_hwnd = transaction.target.hwnd
        self._attempt_context = transaction.context
        self.injector.set_window_context(transaction.context)
        trace.trace(
            f"stage=target hwnd={transaction.target.hwnd} "
            f"scope={transaction.target.hwnd}/{transaction.target.pid}"
        )
        lifecycle.begin_send()
        trace.trace(
            f"transaction: attempt={transaction.attempt_id} "
            f"state={lifecycle.state.value}"
        )
        self._execute_prepared_attempt(
            transaction.text,
            transaction.restore_hwnd,
            transaction.attempt_id,
        )

    def _send_worker(self, text: str, work_hwnd: int, attempt_id: int) -> None:
        """Legacy direct-call adapter; production threads use SendRequest."""
        self._send_worker_request(
            SendRequest(
                attempt_id=attempt_id,
                text=text,
                restore_hwnd=work_hwnd,
            )
        )

    def _poll_results(self) -> None:
        """Consume typed worker completions on Tk's UI thread."""
        try:
            while True:
                completion = self._result_q.get_nowait()
                if not isinstance(completion, SendCompletion):
                    trace.trace("ignoring malformed untyped worker completion")
                    continue
                self._send_finished(completion)
        except queue.Empty:
            pass
        self.after(80, self._poll_results)

    def _send_finished(self, completion: SendCompletion) -> None:
        is_current = (
            completion.attempt_id == self.__dict__.get("_active_attempt_id", 0)
        )
        active_transaction = self.__dict__.get("_active_transaction")
        context = active_transaction.context if (
            active_transaction is not None and
            active_transaction.attempt_id == completion.attempt_id
        ) else self.__dict__.get("_attempt_context")
        release = getattr(self.target, "release", None)
        active_lifecycle = self.__dict__.get("_active_lifecycle")
        lifecycle = active_lifecycle if (
            active_lifecycle is not None and
            active_lifecycle.attempt_id == completion.attempt_id
        ) else None
        evidence = completion.resolved_evidence
        try:
            super()._send_finished(completion)
            if not is_current:
                return
            trace.trace(
                f"stage=verification adapter=telegram state={evidence.state.value} "
                f"confirmed={'yes' if evidence.confirmed else 'no'}"
            )
            if evidence.state is EvidenceState.BLOCKED:
                self._show_feedback(
                    evidence.detail or "Send was blocked before submission.",
                    config.ERROR_COLOR,
                )
            if lifecycle is not None and lifecycle.state is TransactionState.SENDING:
                lifecycle.complete_from_evidence(evidence.state)
                trace.trace(
                    f"transaction: attempt={completion.attempt_id} "
                    f"state={lifecycle.state.value}"
                )
            if self._retry_draft and context is not None:
                self._retry_context = context
            elif not self._retry_draft:
                self._retry_context = None
                self._attempt_context = None
                self.injector.set_window_context(None)
            self._active_transaction = None
            self._active_lifecycle = None
        finally:
            if is_current and callable(release):
                release()


__all__ = ["OrbRelayWindow"]
