"""Production entry point with background application and Telegram chat pickers."""

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .background_picker import BackgroundAppPicker, PickerItem
from .background_windows import enumerate_background_windows
from .generic_target import BackgroundTypingTarget
from .telegram_chats import enumerate_telegram_chats, select_telegram_chat, TelegramChatItem
from .telegram_chat_picker import TelegramChatPicker
from .context import capture
from .transaction import SendCompletion
from . import trace
from .overlay import OrbRelayWindow as _BaseOverlay


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay with title-free app discovery and Telegram chat selection."""

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
        self._telegram_chat_picker = TelegramChatPicker(
            self,
            refresh=lambda: enumerate_telegram_chats(self._work_hwnd),
            on_select=self._select_telegram_chat,
        )
        self._background_typer = BackgroundTypingTarget()
        self._generic_attempt_id = 0
        self._background_process_name = ""
        self._pending_chat = None

    def _select_background_window(self, item: PickerItem) -> None:
        """Bind an actionable process/window without foregrounding it."""
        if not item.actionable or not item.hwnd or not item.pid:
            return
        self._background_typer.release()
        self._background_process_name = item.process_name
        self._work_hwnd = item.hwnd
        self._generic_attempt_id = 0
        if item.process_name == "telegram.exe":
            self._pending_chat = None
            self._telegram_chat_picker.show()
            return
        self._background_typer.bind(item.hwnd, item.pid)
        self._update_status()
        if self._state != "bar" and not self._sending:
            self._show_bar()

    def _select_telegram_chat(self, chat: TelegramChatItem) -> None:
        """Select a Telegram chat in the background, then rebuild its context guard."""
        if self._sending:
            return
        self._pending_chat = chat
        try:
            self.target.release()
            select_telegram_chat(chat)
        except Exception as exc:
            self._pending_chat = None
            trace.trace(f"telegram chat selection failed safely: {exc}")
            self._show_feedback(
                "The selected Telegram chat could not be opened safely.",
            )
            return
        self.after(160, self._finish_telegram_chat_selection)

    def _finish_telegram_chat_selection(self) -> None:
        chat = self._pending_chat
        self._pending_chat = None
        if chat is None or self._sending:
            return
        try:
            self.target.release()
            selected = self.target.select_for_send(preferred_hwnd=chat.hwnd)
            if selected != chat.hwnd:
                raise RuntimeError("Telegram selected a different window")
            self._work_hwnd = chat.hwnd
            self._attempt_context = capture(chat.hwnd)
            self.injector.set_window_context(self._attempt_context)
            self._update_status()
            if self._state != "bar":
                self._show_bar()
        except Exception as exc:
            trace.trace(f"telegram chat context recapture failed safely: {exc}")
            self._show_feedback(
                "Telegram changed before the selected chat could be guarded.",
            )

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
