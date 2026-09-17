"""Production entry point with background application and chat pickers."""

import tkinter as tk

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .app_adapters import actionable_adapter_for_process
from .app_targets import target_for_adapter
from .background_picker import BackgroundAppPicker, PickerItem
from .background_windows import enumerate_background_windows
from .conversation_picker import ConversationPicker
from .conversation_rows import ConversationItem, enumerate_conversations, select_conversation
from .telegram_chats import enumerate_telegram_chats, select_telegram_chat, TelegramChatItem
from .telegram_chat_picker import TelegramChatPicker
from .context import capture
from .adapter_evidence import evidence_for_adapter
from .transaction import SendCompletion
from . import trace
from . import onboarding
from .overlay import OrbRelayWindow as _BaseOverlay


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay with background application and conversation selection."""

    def __init__(self):
        super().__init__()
        self._background_picker = BackgroundAppPicker(
            self,
            refresh=lambda: enumerate_background_windows(
                exclude_hwnds={self.winfo_id()},
                include_minimized=True,
            ),
            on_select=self._select_background_window,
        )
        self._background_picker.bind(self.orb)
        self._telegram_chat_picker = TelegramChatPicker(
            self,
            refresh=lambda: enumerate_telegram_chats(self._work_hwnd),
            on_select=self._select_telegram_chat,
        )
        self._conversation_picker = ConversationPicker(
            self,
            refresh=lambda: enumerate_conversations(self._work_hwnd),
            on_select=self._select_conversation,
        )
        self._background_typer = target_for_adapter(None)
        self._generic_attempt_id = 0
        self._background_process_name = ""
        self._background_adapter_key = ""
        self._generic_retry_scope = None
        self._generic_retry_process_name = ""
        self._generic_retry_adapter_key = ""
        self._pending_chat = None
        self._pending_conversation = None
        self._selection_generation = 0
        self._background_identity_label = tk.Label(
            self.bar,
            bg=self.bar.cget("bg"),
            fg="#a1a1aa",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self._onboarding_job = self.after(250, self._show_onboarding_once)

    def _show_onboarding_once(self) -> None:
        self._onboarding_job = None
        try:
            onboarding.show(self)
        except Exception as exc:
            trace.trace(f"first-run guide could not be shown safely: {exc}")

    def _show_bar(self):
        super()._show_bar()
        spec = actionable_adapter_for_process(getattr(self, "_background_process_name", ""))
        label = spec.label if spec is not None else ""
        if label:
            self._background_identity_label.config(text=label)
            self._background_identity_label.place(x=8, y=12, width=66, height=16)
            self.entry.place(
                x=78,
                y=10,
                width=max(40, self.winfo_width() - 86),
                height=20,
            )
        else:
            self._background_identity_label.place_forget()

    def _advance_selection_generation(self) -> int:
        generation = int(self.__dict__.get("_selection_generation", 0)) + 1
        self.__dict__["_selection_generation"] = generation
        return generation

    def _selection_generation_value(self) -> int:
        return int(self.__dict__.get("_selection_generation", 0))

    def _bind_adapter_metadata(self, spec) -> None:
        """Attach adapter semantics without changing the legacy bind call shape."""
        binder = getattr(self._background_typer, "bind_adapter", None)
        if binder is not None:
            binder(spec)

    @staticmethod
    def _probe_reason(probe) -> str:
        """Return a known readiness reason while tolerating legacy probe mocks."""
        reason = getattr(probe, "reason", "ready")
        return reason if reason in {"ready", "unavailable", "no-input", "inspection-error"} else "ready"

    @classmethod
    def _probe_feedback(cls, probe) -> str:
        """Map content-free readiness codes to user-facing guidance."""
        reason = cls._probe_reason(probe)
        if reason == "unavailable":
            return "That background app closed or changed before it could be used."
        if reason == "no-input":
            return "That app is open, but no safe typing control is available there yet."
        if reason == "inspection-error":
            return "That app is open, but its background typing controls could not be inspected safely."
        return "That app could not expose a safe background typing control."

    def _select_background_window(self, item: PickerItem) -> None:
        """Choose an actionable process/window without foregrounding it."""
        if not item.actionable or not item.hwnd or not item.pid:
            return
        spec = actionable_adapter_for_process(item.process_name)
        if spec is None or not spec.implemented or not spec.supports_background_type:
            return
        self._advance_selection_generation()
        self._background_typer.release()
        self._background_typer = target_for_adapter(spec)
        self._generic_retry_scope = None
        self._generic_retry_process_name = ""
        self._generic_retry_adapter_key = ""
        self._background_process_name = item.process_name
        self._background_adapter_key = spec.key
        self._work_hwnd = item.hwnd
        self._generic_attempt_id = 0

        if spec.chat_picker == "telegram":
            self._pending_chat = None
            self._telegram_chat_picker.show()
            return
        if spec.chat_picker == "conversations":
            self._pending_conversation = None
            self._conversation_picker.show()
            return

        self._bind_generic_target(item.hwnd, item.pid, spec)

    def _bind_generic_target(self, hwnd: int, pid: int, spec=None) -> None:
        self._background_typer.bind(hwnd, pid)
        self._bind_adapter_metadata(spec)
        self._update_status()
        try:
            probe = self._background_typer.probe()
        except Exception as exc:
            trace.trace(f"background target readiness probe failed safely: {exc}")
            self._show_feedback("That app could not expose a safe background typing control.")
            return
        reason = self._probe_reason(probe)
        if not probe.available or probe.candidate_count <= 0 or reason != "ready":
            self._show_feedback(self._probe_feedback(probe))
            return
        if self._state != "bar" and not self._sending:
            self._show_bar()

    def _select_conversation(self, conversation: ConversationItem) -> None:
        if self._sending:
            return
        token = self._advance_selection_generation()
        self._pending_conversation = conversation
        try:
            select_conversation(conversation)
        except Exception as exc:
            self._pending_conversation = None
            trace.trace(f"background conversation selection failed safely: {exc}")
            self._show_feedback("The selected conversation could not be opened safely.")
            return
        self.after(160, lambda generation=token: self._finish_conversation_selection(generation))

    def _finish_conversation_selection(self, generation=None) -> None:
        if generation is not None and generation != self._selection_generation_value():
            return
        conversation = self._pending_conversation
        self._pending_conversation = None
        if conversation is None or self._sending:
            return
        try:
            spec = actionable_adapter_for_process(self._background_process_name)
            scope = self._background_typer.bind(conversation.hwnd, conversation.pid)
            self._bind_adapter_metadata(spec)
            if scope.hwnd != self._work_hwnd or scope.pid != conversation.pid:
                raise RuntimeError("conversation selected a different window or process")
            self._update_status()
            try:
                probe = self._background_typer.probe()
            except Exception as exc:
                trace.trace(f"conversation target readiness probe failed safely: {exc}")
                raise RuntimeError("selected conversation has no safe background typing control")
            if not probe.available or probe.candidate_count <= 0 or self._probe_reason(probe) != "ready":
                raise RuntimeError(self._probe_feedback(probe))
            if self._state != "bar":
                self._show_bar()
        except Exception as exc:
            trace.trace(f"conversation target bind failed safely: {exc}")
            self._show_feedback(str(exc) if str(exc) else "The selected conversation has no safe background typing control yet.")

    def _select_telegram_chat(self, chat: TelegramChatItem) -> None:
        if self._sending:
            return
        token = self._advance_selection_generation()
        self._pending_chat = chat
        try:
            self.target.release()
            select_telegram_chat(chat)
        except Exception as exc:
            self._pending_chat = None
            trace.trace(f"telegram chat selection failed safely: {exc}")
            self._show_feedback("The selected Telegram chat could not be opened safely.")
            return
        self.after(160, lambda generation=token: self._finish_telegram_chat_selection(generation))

    def _finish_telegram_chat_selection(self, generation=None) -> None:
        if generation is not None and generation != self._selection_generation_value():
            return
        chat = self._pending_chat
        self._pending_chat = None
        if chat is None or self._sending:
            return
        try:
            self.target.release()
            selected = self.target.select_for_send(preferred_hwnd=chat.hwnd)
            if selected != chat.hwnd:
                raise RuntimeError("Telegram selected a different window")
            self.target.bind_chat_identity(chat)
            if not self.target.chat_identity_matches():
                self.target.release()
                raise RuntimeError("Telegram changed away from the selected chat")
            self._work_hwnd = chat.hwnd
            self._attempt_context = capture(chat.hwnd)
            self.injector.set_window_context(self._attempt_context)
            self._update_status()
            if self._state != "bar":
                self._show_bar()
        except Exception as exc:
            trace.trace(f"telegram chat context recapture failed safely: {exc}")
            self._show_feedback("Telegram changed before the selected chat could be guarded.")

    def _send_worker_request(self, request):
        """Route non-Telegram picker selections through their app-specific target."""
        process_name = getattr(self, "_background_process_name", "")
        adapter_key = getattr(self, "_background_adapter_key", "")
        spec = actionable_adapter_for_process(process_name)
        if not process_name or spec is None:
            return super()._send_worker_request(request)
        if adapter_key == "telegram":
            if getattr(request, "valid", False) and not self.target.chat_identity_matches():
                self._queue_completion(
                    getattr(request, "attempt_id", 0),
                    None,
                    "The selected Telegram chat changed before sending, so the draft was stopped safely.",
                )
                return
            return super()._send_worker_request(request)
        if not getattr(request, "valid", False):
            return super()._send_worker_request(request)

        self._generic_attempt_id = request.attempt_id
        try:
            scope = self._background_typer.scope()
            if not self._background_typer.scope_matches(scope.hwnd, scope.pid) or scope.hwnd != request.restore_hwnd:
                raise RuntimeError("selected background target changed before send")
            self._background_typer.pin_best_input()
            strategy = self._background_typer.send(request.text)
            evidence = evidence_for_adapter(spec, strategy=strategy)
            self._result_q.put(
                SendCompletion(
                    attempt_id=request.attempt_id,
                    strategy=strategy,
                    error=evidence.detail,
                    evidence_state=evidence.state,
                    evidence=evidence,
                )
            )
        except Exception as exc:
            self._background_typer.clear_pinned_input()
            trace.trace(f"background typing failed safely: {exc}")
            self._result_q.put(
                SendCompletion.from_result(
                    attempt_id=request.attempt_id,
                    error=str(exc),
                )
            )

    def _retry_failed_draft(self) -> None:
        if self._sending or not self._retry_draft:
            return
        scope = self._generic_retry_scope
        if scope is None:
            return super()._retry_failed_draft()
        spec = actionable_adapter_for_process(self._generic_retry_process_name)
        if spec is None or not spec.implemented or not spec.supports_background_type:
            self._show_feedback("The original background app is no longer supported safely.")
            return
        self._background_typer = target_for_adapter(spec)
        self._background_typer.bind(scope.hwnd, scope.pid)
        self._bind_adapter_metadata(spec)
        self._background_process_name = self._generic_retry_process_name
        self._background_adapter_key = self._generic_retry_adapter_key
        self._work_hwnd = scope.hwnd
        self._hide_feedback()
        self._show_bar()
        self._set_retry_menu_enabled(True)

    def _send_finished(self, completion):
        """Use base UI handling for generic attempts, without Telegram release."""
        if completion.attempt_id != getattr(self, "_generic_attempt_id", 0):
            return super()._send_finished(completion)
        retry_scope = None
        retry_process_name = self._background_process_name
        retry_adapter_key = self._background_adapter_key
        try:
            retry_scope = self._background_typer.scope()
            _BaseOverlay._send_finished(self, completion)
            if getattr(self, "_retry_draft", None):
                self._generic_retry_scope = retry_scope
                self._generic_retry_process_name = retry_process_name
                self._generic_retry_adapter_key = retry_adapter_key
            else:
                self._generic_retry_scope = None
                self._generic_retry_process_name = ""
                self._generic_retry_adapter_key = ""
        finally:
            self._generic_attempt_id = 0
            self._background_typer.release()
            self._background_process_name = ""
            self._background_adapter_key = ""


__all__ = ["OrbRelayWindow"]
