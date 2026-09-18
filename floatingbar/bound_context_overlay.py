"""Production entry point with background application and chat pickers."""

import tkinter as tk

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .app_adapters import actionable_adapter_for_process
from .app_targets import target_for_adapter
from .background_picker import BackgroundAppPicker, PickerItem, to_picker_items
from .background_windows import enumerate_background_windows, BackgroundWindow
from .conversation_picker import ConversationPicker
from .conversation_rows import ConversationItem, enumerate_conversations, select_conversation
from .telegram_chats import enumerate_telegram_chats, select_telegram_chat, TelegramChatItem
from .telegram_chat_picker import TelegramChatPicker
from .context import capture
from .adapter_evidence import evidence_for_adapter
from .transaction import SendCompletion
from .recent_targets import RecentTargetHistory
from .pinned_targets import PinnedTargetStore
from .quick_replies import QuickReply, QuickReplyManager, QuickReplyStore
from . import trace
from . import onboarding
from . import winapi
from .overlay import OrbRelayWindow as _BaseOverlay


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay with background application and conversation selection."""

    def __init__(self):
        super().__init__()
        self._recent_targets = RecentTargetHistory()
        self._pinned_targets = PinnedTargetStore()
        self._quick_reply_store = QuickReplyStore()
        self._quick_reply_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="Quick replies", menu=self._quick_reply_menu)
        self.menu.add_command(label="Manage quick replies", command=self._open_quick_reply_manager)
        self._refresh_quick_reply_menu()
        self._background_picker = BackgroundAppPicker(
            self,
            refresh=lambda: enumerate_background_windows(
                exclude_hwnds={self.winfo_id()},
                include_minimized=True,
            ),
            on_select=self._select_background_window,
            recent=self._recent_picker_items,
            pinned=self._pinned_picker_items,
            pin_toggle=self._toggle_pinned_application,
        )
        self._background_picker.bind(self.orb)
        self._telegram_chat_picker = TelegramChatPicker(
            self,
            refresh=lambda: enumerate_telegram_chats(self._work_hwnd),
            on_select=self._select_telegram_chat,
        )
        self._conversation_picker = ConversationPicker(
            self,
            refresh=lambda: enumerate_conversations(
                self._work_hwnd,
                limit=ConversationPicker.CATALOG_LIMIT,
            ),
            on_select=self._select_conversation,
            recent=self._recent_conversation_items,
            pinned=self._pinned_conversation_items,
            pin_toggle=self._toggle_pinned_conversation,
        )
        self._background_typer = target_for_adapter(None)
        self._generic_attempt_id = 0
        self._background_process_name = ""
        self._background_adapter_key = ""
        self._background_window_class = ""
        self._generic_retry_scope = None
        self._generic_retry_process_name = ""
        self._generic_retry_adapter_key = ""
        self._generic_retry_window_class = ""
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

    def _refresh_quick_reply_menu(self) -> None:
        menu = self._quick_reply_menu
        menu.delete(0, "end")
        replies = self._quick_reply_store.items()
        if replies:
            for reply in replies:
                menu.add_command(
                    label=reply.label,
                    command=lambda item=reply: self._use_quick_reply(item),
                )
            menu.add_separator()
        else:
            menu.add_command(label="No saved replies", state="disabled")
        menu.add_command(label="Manage quick replies", command=self._open_quick_reply_manager)

    def _use_quick_reply(self, reply: QuickReply) -> None:
        if self._sending:
            return
        if self._state != "bar":
            self._expand()
        if self._state != "bar":
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, reply.text)
        self.entry.select_range(0, "end")
        self._reset_idle()

    def _open_quick_reply_manager(self) -> None:
        if self._sending:
            return
        QuickReplyManager(
            self,
            self._quick_reply_store,
            on_use=self._use_quick_reply,
            on_change=self._refresh_quick_reply_menu,
        )

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

    def _recent_picker_items(self) -> tuple[PickerItem, ...]:
        """Return validated session-only application targets for the hover picker."""
        items = []
        for target in self._recent_targets.live_applications():
            spec = actionable_adapter_for_process(target.process_name)
            if spec is None or not spec.implemented or spec.key != target.adapter_key:
                continue
            items.append(
                PickerItem(
                    hwnd=target.scope.hwnd,
                    pid=target.scope.pid,
                    label=spec.label,
                    actionable=spec.supports_background_type,
                    foreground=False,
                    process_name=target.process_name,
                    adapter_key=spec.key,
                    recent=True,
                    window_class=str(target.window_class or ""),
                )
            )
        return tuple(items)

    def _pinned_picker_items(
        self,
        windows: tuple[BackgroundWindow, ...] | list[BackgroundWindow],
    ) -> tuple[PickerItem, ...]:
        """Resolve application pins only when exactly one live scope is available."""
        items = []
        for pin in self._pinned_targets.items(kind="application"):
            matches = [
                item
                for item in windows
                if item.process_name.casefold() == pin.process_name
            ]
            if pin.window_class:
                matches = [
                    item for item in matches
                    if item.window_class == pin.window_class
                ]
            if len(matches) != 1:
                continue
            item = to_picker_items(matches)[0]
            spec = actionable_adapter_for_process(item.process_name)
            if spec is None or spec.key != pin.adapter_key or not spec.implemented:
                continue
            items.append(
                PickerItem(
                    hwnd=item.hwnd,
                    pid=item.pid,
                    label=spec.label,
                    actionable=spec.supports_background_type,
                    foreground=item.foreground,
                    process_name=item.process_name,
                    adapter_key=spec.key,
                    pinned=True,
                    window_class=item.window_class,
                )
            )
        return tuple(items)

    def _recent_conversation_items(self) -> tuple[ConversationItem, ...]:
        """Return only fresh conversation rows for the currently selected app."""
        process_name = str(getattr(self, "_background_process_name", "") or "").casefold()
        adapter_key = str(getattr(self, "_background_adapter_key", "") or "")
        hwnd = int(getattr(self, "_work_hwnd", 0) or 0)
        if not process_name or not adapter_key or not hwnd:
            return ()
        rows = []
        for target, conversation in self._recent_targets.live_conversations():
            if target.adapter_key != adapter_key:
                continue
            if target.process_name != process_name:
                continue
            if target.scope.hwnd != hwnd or target.scope.pid != conversation.pid:
                continue
            rows.append(conversation)
        return tuple(rows)

    def _pinned_conversation_items(self) -> tuple[ConversationItem, ...]:
        """Resolve conversation pins only when a unique live row matches exactly."""
        process_name = str(getattr(self, "_background_process_name", "") or "").casefold()
        adapter_key = str(getattr(self, "_background_adapter_key", "") or "")
        if not process_name or not adapter_key:
            return ()
        try:
            live = tuple(enumerate_conversations(
                self._work_hwnd,
                limit=ConversationPicker.CATALOG_LIMIT,
            ) or ())
        except Exception:
            return ()
        rows = []
        for pin in self._pinned_targets.items(kind="conversation"):
            if pin.process_name != process_name or pin.adapter_key != adapter_key:
                continue
            matches = [item for item in live if item.name == pin.label]
            if pin.control_identity is not None:
                matches = [
                    item for item in matches
                    if item.control_identity == pin.control_identity
                ]
            if pin.container_identity is not None:
                matches = [
                    item for item in matches
                    if item.container_identity == pin.container_identity
                ]
            if len(matches) == 1:
                rows.append(matches[0])
        return tuple(rows)

    def _toggle_pinned_application(self, item: PickerItem) -> None:
        spec = actionable_adapter_for_process(item.process_name)
        if spec is None or spec.key != item.adapter_key:
            return
        self._pinned_targets.toggle_application(
            adapter_key=spec.key,
            process_name=item.process_name,
            label=spec.label,
            window_class=item.window_class,
        )

    def _toggle_pinned_conversation(self, conversation: ConversationItem) -> None:
        spec = actionable_adapter_for_process(self._background_process_name)
        if spec is None:
            return
        self._pinned_targets.toggle_conversation(
            adapter_key=spec.key,
            process_name=self._background_process_name,
            label=conversation.name,
            control_identity=conversation.control_identity,
            container_identity=conversation.container_identity,
        )

    def _remember_bound_application(self, spec, hwnd: int, pid: int, window_class: str = "") -> None:
        """Remember only a successfully probed application scope."""
        if spec is None or not spec.implemented or not spec.supports_background_type:
            return
        self._recent_targets.record_application(
            hwnd=hwnd,
            pid=pid,
            process_name=self._background_process_name,
            label=spec.label,
            adapter_key=spec.key,
            window_class=window_class,
        )

    def _select_background_window(self, item: PickerItem) -> None:
        """Choose an actionable process/window without foregrounding it."""
        if not item.actionable or not item.hwnd or not item.pid:
            return
        spec = actionable_adapter_for_process(item.process_name)
        if spec is None or not spec.implemented or not spec.supports_background_type:
            return
        self._advance_selection_generation()
        self._background_typer.release()
        self._generic_retry_scope = None
        self._generic_retry_process_name = ""
        self._generic_retry_adapter_key = ""
        self._generic_retry_window_class = ""
        self._pending_chat = None
        self._pending_conversation = None
        self._background_process_name = ""
        self._background_adapter_key = ""
        self._background_window_class = ""
        self._work_hwnd = 0
        self._generic_attempt_id = 0
        self._update_status()
        try:
            if winapi.user32.IsWindow(item.hwnd) and winapi.get_window_pid(item.hwnd) != item.pid:
                self._show_feedback("That background app changed before it could be selected.")
                return
            if not winapi.user32.IsWindow(item.hwnd):
                self._show_feedback("That background app is no longer available.")
                return
            raw_class = getattr(item, "window_class", "")
            expected_class = raw_class.strip() if isinstance(raw_class, str) else ""
            if expected_class:
                current_class = str(winapi.get_window_class_name(item.hwnd) or "").strip()
                if current_class != expected_class:
                    self._show_feedback("That background app changed before it could be selected.")
                    return
        except Exception:
            self._show_feedback("That background app could not be verified safely.")
            return
        self._background_typer = target_for_adapter(spec)
        self._background_process_name = item.process_name
        self._background_adapter_key = spec.key
        self._background_window_class = expected_class
        self._work_hwnd = item.hwnd
        self._generic_attempt_id = 0

        if spec.chat_picker == "telegram":
            self._pending_chat = None
            self._telegram_chat_picker.show()
            return
        if spec.chat_picker == "conversations":
            self._pending_conversation = None
            self._conversation_picker.set_title(spec.label)
            self._conversation_picker.show()
            return

        self._bind_generic_target(item.hwnd, item.pid, spec, item.window_class)

    def _bind_generic_target(self, hwnd: int, pid: int, spec=None, window_class: str = "") -> None:
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
        self._remember_bound_application(spec, hwnd, pid, window_class)
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
            expected_class = str(getattr(self, "_background_window_class", "") or "").strip()
            if expected_class:
                current_class = str(winapi.get_window_class_name(conversation.hwnd) or "").strip()
                if current_class != expected_class:
                    raise RuntimeError("selected conversation window changed before binding")
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
            if spec is not None:
                self._recent_targets.record_conversation(
                    conversation,
                    adapter_key=spec.key,
                    process_name=self._background_process_name,
                )
            if self._state != "bar":
                self._show_bar()
        except Exception as exc:
            try:
                self._background_typer.release()
            except Exception:
                pass
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
            expected_class = str(getattr(self, "_background_window_class", "") or "").strip()
            if expected_class:
                current_class = str(winapi.get_window_class_name(chat.hwnd) or "").strip()
                if current_class != expected_class:
                    raise RuntimeError("Telegram window changed before binding the selected chat")
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
            spec = actionable_adapter_for_process(self._background_process_name)
            if spec is not None:
                self._recent_targets.record_application(
                    hwnd=chat.hwnd,
                    pid=chat.pid,
                    process_name=self._background_process_name,
                    label=spec.label,
                    adapter_key=spec.key,
                )
            self._update_status()
            if self._state != "bar":
                self._show_bar()
        except Exception as exc:
            try:
                self.target.release()
            except Exception:
                pass
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
        if (
            spec is None
            or not spec.implemented
            or not spec.supports_background_type
            or spec.key != self._generic_retry_adapter_key
        ):
            self._show_feedback("The original background app is no longer supported safely.")
            return
        target = target_for_adapter(spec)
        rebound = target.bind(scope.hwnd, scope.pid)
        if rebound != scope or not target.scope_matches(scope.hwnd, scope.pid):
            target.release()
            self._show_feedback("The original background app changed before the retry could start.")
            return
        try:
            probe = target.probe()
        except Exception:
            target.release()
            self._show_feedback("The original background app could not be inspected safely for retry.")
            return
        if not probe.available or probe.candidate_count <= 0 or self._probe_reason(probe) != "ready":
            target.release()
            self._show_feedback(self._probe_feedback(probe))
            return
        self._background_typer = target
        self._bind_adapter_metadata(spec)
        self._background_process_name = self._generic_retry_process_name
        self._background_adapter_key = self._generic_retry_adapter_key
        expected_class = str(getattr(self, "_generic_retry_window_class", "") or "").strip()
        if expected_class:
            current_class = str(winapi.get_window_class_name(scope.hwnd) or "").strip()
            if current_class != expected_class:
                target.release()
                self._show_feedback("The original background window changed before the retry could start.")
                return
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
        retry_window_class = ""
        try:
            retry_scope = self._background_typer.scope()
            if retry_scope.valid:
                retry_window_class = str(winapi.get_window_class_name(retry_scope.hwnd) or "").strip()
            _BaseOverlay._send_finished(self, completion)
            if getattr(self, "_retry_draft", None):
                self._generic_retry_scope = retry_scope
                self._generic_retry_process_name = retry_process_name
                self._generic_retry_adapter_key = retry_adapter_key
                self._generic_retry_window_class = retry_window_class
            else:
                self._generic_retry_scope = None
                self._generic_retry_process_name = ""
                self._generic_retry_adapter_key = ""
                self._generic_retry_window_class = ""
        finally:
            self._generic_attempt_id = 0
            self._background_typer.release()
            self._background_process_name = ""
            self._background_adapter_key = ""
            self._background_window_class = ""
            self._work_hwnd = 0


__all__ = ["OrbRelayWindow"]
