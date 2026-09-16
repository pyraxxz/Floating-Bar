"""Production entry point with the background-app hover picker.

Telegram keeps the full context-aware transaction path. Common background
applications use a separate exact-scope typing adapter, without being forced
through Telegram UIA discovery or its context assumptions.
"""

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .background_picker import BackgroundAppPicker, PickerItem
from .background_windows import enumerate_background_windows
from .generic_target import BackgroundTypingTarget
from .transaction import SendCompletion
from . import trace
from .overlay import OrbRelayWindow as _BaseOverlay


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay with title-free background-app discovery."""

    def __init__(self):
        super().__init__()
        self._background_picker = BackgroundAppPicker(
            self,
            refresh=lambda: enumerate_background_windows(
                exclude_hwnds={self.winfo_id()},
            ),
            on_select=self._select_background_window,
        )
        self._background_picker.bind(self.orb)
        self._background_typer = BackgroundTypingTarget()
        self._generic_attempt_id = 0
        self._background_process_name = ""

    def _select_background_window(self, item: PickerItem) -> None:
        """Bind an actionable process/window without foregrounding it."""
        if not item.actionable or not item.hwnd or not item.pid:
            return
        if item.process_name == "telegram.exe":
            self._background_typer.release()
        else:
            self._background_typer.bind(item.hwnd, item.pid)
        self._generic_attempt_id = 0
        self._work_hwnd = item.hwnd
        self._background_process_name = item.process_name
        self._update_status()
        if self._state != "bar" and not self._sending:
            self._show_bar()

    def _send_worker_request(self, request):
        """Route non-Telegram picker selections through exact-scope typing."""
        process_name = getattr(self, "_background_process_name", "")
        if process_name == "telegram.exe" or not process_name:
            return super()._send_worker_request(request)
        if not getattr(request, "valid", False):
            return super()._send_worker_request(request)

        self._generic_attempt_id = request.attempt_id
        try:
            scope = self._background_typer.scope()
            if not self._background_typer.scope_matches(
                scope.hwnd,
                scope.pid,
            ) or scope.hwnd != request.restore_hwnd:
                raise RuntimeError("selected background target changed before send")
            strategy = self._background_typer.send(request.text)
            self._result_q.put(
                SendCompletion.from_result(
                    attempt_id=request.attempt_id,
                    strategy=strategy,
                )
            )
        except Exception as exc:
            trace.trace(f"background typing failed safely: {exc}")
            self._result_q.put(
                SendCompletion.from_result(
                    attempt_id=request.attempt_id,
                    error=str(exc),
                )
            )

    def _send_finished(self, completion):
        """Use base UI handling for generic attempts, without Telegram release."""
        if completion.attempt_id != getattr(self, "_generic_attempt_id", 0):
            return super()._send_finished(completion)
        try:
            _BaseOverlay._send_finished(self, completion)
        finally:
            self._generic_attempt_id = 0
            self._background_typer.release()
            self._background_process_name = ""


__all__ = ["OrbRelayWindow"]
