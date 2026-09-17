"""Hover picker for visible background applications.

The picker is intentionally process-level: it never displays window titles,
chat names, or message content. Known applications expose a named adapter;
unknown applications may expose a generic Type action, with structural input
inspection remaining the readiness gate before the bar opens.
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .app_adapters import actionable_adapter_for_process
from .background_windows import BackgroundWindow


_LABELS = {
    "notepad.exe": "Notepad",
    "code.exe": "VS Code",
}


@dataclass(frozen=True)
class PickerItem:
    """UI-safe projection of a background window."""

    hwnd: int
    pid: int
    label: str
    actionable: bool
    foreground: bool
    process_name: str = ""
    adapter_key: str = ""
    recent: bool = False


@dataclass
class HoverState:
    """Deterministic pointer-presence state for the three-level picker."""

    owner: bool = False
    popup: bool = False
    actions: bool = False

    @property
    def outside(self) -> bool:
        return not (self.owner or self.popup or self.actions)

    def enter_owner(self) -> None:
        self.owner = True

    def leave_owner(self) -> None:
        self.owner = False

    def enter_popup(self) -> None:
        self.popup = True

    def leave_popup(self) -> None:
        self.popup = False

    def enter_actions(self) -> None:
        self.actions = True

    def leave_actions(self) -> None:
        self.actions = False


def _base_label(item: BackgroundWindow) -> tuple[str, bool]:
    """Return a title-free app label and whether it has an actionable adapter."""
    spec = actionable_adapter_for_process(item.process_name)
    actionable = bool(spec and spec.implemented and spec.supports_background_type)
    label = spec.label if spec else _LABELS.get(
        item.process_name,
        item.label.removesuffix(".exe").title(),
    )
    return label, actionable


def to_picker_items(windows: Sequence[BackgroundWindow]) -> tuple[PickerItem, ...]:
    """Convert catalog entries into title-free picker rows.

    When multiple top-level windows resolve to the same app label, append a
    deterministic ordinal. This keeps separate windows selectable without
    exposing window titles or other user content.
    """
    prepared = []
    counts = {}
    for item in windows:
        label, actionable = _base_label(item)
        counts[label] = counts.get(label, 0) + 1
        prepared.append((item, label, actionable))

    seen = {}
    items = []
    for item, label, actionable in prepared:
        seen[label] = seen.get(label, 0) + 1
        display_label = (
            f"{label} {seen[label]}"
            if counts[label] > 1
            else label
        )
        spec = actionable_adapter_for_process(item.process_name)
        items.append(
            PickerItem(
                hwnd=item.hwnd,
                pid=item.pid,
                label=display_label,
                actionable=actionable,
                foreground=item.foreground,
                process_name=item.process_name,
                adapter_key=spec.key if actionable and spec else "",
            )
        )
    return tuple(items)


def action_for_item(item: PickerItem) -> str:
    """Return the safe action exposed when hovering an application row."""
    spec = actionable_adapter_for_process(item.process_name)
    if not item.actionable or not spec or not spec.implemented:
        return "Preview"
    if not spec.supports_background_type:
        return "Preview"
    return spec.action


class BackgroundAppPicker:
    """Small hover popup that never foregrounds the selected target app."""

    HOVER_DELAY_MS = 140
    TRANSITION_GRACE_MS = 220
    ACTION_GRACE_MS = 220
    WIDTH = 210
    ROW_HEIGHT = 30
    SECTION_HEIGHT = 22
    MAX_RECENT = 2
    MAX_VISIBLE = 6

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[BackgroundWindow]],
        on_select: Callable[[PickerItem], None],
        recent: Optional[Callable[[], Sequence[PickerItem]]] = None,
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.recent = recent or (lambda: ())
        self.window: Optional[tk.Toplevel] = None
        self._show_job = None
        self._hide_job = None
        self._action_window: Optional[tk.Toplevel] = None
        self._action_item: Optional[PickerItem] = None
        self._hover = HoverState()

    def bind(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", self._owner_enter, add="+")
        widget.bind("<Leave>", self._owner_leave, add="+")

    def _owner_enter(self, _event=None) -> None:
        self._hover.enter_owner()
        self._cancel_show()
        self._cancel_hide()
        self._show_job = self.owner.after(self.HOVER_DELAY_MS, self.show)

    def _owner_leave(self, _event=None) -> None:
        self._hover.leave_owner()
        self._schedule_hide(self.TRANSITION_GRACE_MS)

    def _popup_enter(self, _event=None) -> None:
        self._hover.enter_popup()
        self._cancel_hide()

    def _popup_leave(self, _event=None) -> None:
        self._hover.leave_popup()
        self._schedule_hide(self.TRANSITION_GRACE_MS)

    def _actions_enter(self, _event=None) -> None:
        self._hover.enter_actions()
        self._cancel_hide()

    def _actions_leave(self, _event=None) -> None:
        self._hover.leave_actions()
        self._schedule_hide(self.ACTION_GRACE_MS)

    def _schedule_hide(self, delay_ms: int = TRANSITION_GRACE_MS) -> None:
        self._cancel_show()
        self._cancel_hide()
        self._hide_job = self.owner.after(delay_ms, self._maybe_hide)

    def _maybe_hide(self) -> None:
        self._hide_job = None
        if self._hover.outside:
            self.hide()

    def _cancel_show(self) -> None:
        if self._show_job is not None:
            try:
                self.owner.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

    def _cancel_hide(self) -> None:
        if self._hide_job is not None:
            try:
                self.owner.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None

    @staticmethod
    def _merge_items(
        recent_items: Sequence[PickerItem],
        live_items: Sequence[PickerItem],
    ) -> tuple[PickerItem, ...]:
        """Prefer recent identity when the same exact scope is currently live."""
        recent = []
        recent_scopes = set()
        for item in recent_items:
            key = (item.hwnd, item.pid)
            if not item.actionable or key in recent_scopes:
                continue
            recent_scopes.add(key)
            recent.append(item)
            if len(recent) >= BackgroundAppPicker.MAX_RECENT:
                break

        live = []
        for item in live_items:
            key = (item.hwnd, item.pid)
            if key in recent_scopes:
                continue
            live.append(item)
            if len(recent) + len(live) >= BackgroundAppPicker.MAX_VISIBLE:
                break
        return tuple(recent) + tuple(live)

    def show(self) -> None:
        self._show_job = None
        if not self._hover.owner:
            return
        try:
            windows = self.refresh()
        except Exception:
            windows = ()
        live_items = to_picker_items(windows)
        try:
            recent_items = tuple(self.recent() or ())
        except Exception:
            recent_items = ()
        items = self._merge_items(recent_items, live_items)
        if not items:
            self.hide()
            return

        self.hide()
        self._hover.enter_owner()
        popup = tk.Toplevel(self.owner)
        self.window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg="#18181b")
        try:
            popup.wm_attributes("-toolwindow", True)
        except Exception:
            pass

        x = self.owner.winfo_rootx() + self.owner.winfo_width() + 8
        y = self.owner.winfo_rooty()
        recent_count = sum(1 for item in items if item.recent)
        live_count = len(items) - recent_count
        sections = int(recent_count > 0) + int(recent_count > 0 and live_count > 0)
        height = len(items) * self.ROW_HEIGHT + sections * self.SECTION_HEIGHT + 8
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        popup.bind("<Enter>", self._popup_enter, add="+")
        popup.bind("<Leave>", self._popup_leave, add="+")

        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        current_section = None
        for item in items:
            section = "Recent" if item.recent else "Open apps"
            if section != current_section:
                if current_section is not None:
                    tk.Frame(frame, bg="#27272a", height=1).pack(fill="x", pady=2)
                tk.Label(
                    frame,
                    text=section,
                    anchor="w",
                    bg="#18181b",
                    fg="#71717a",
                    font=("Segoe UI", 8, "bold"),
                ).pack(fill="x", padx=4, pady=(1, 2))
                current_section = section
            state = "normal" if item.actionable else "disabled"
            suffix = "  " + action_for_item(item)
            button = tk.Button(
                frame,
                text=item.label + suffix,
                anchor="w",
                relief="flat",
                bd=0,
                bg="#18181b",
                fg="#f4f4f5" if item.actionable else "#71717a",
                activebackground="#27272a",
                activeforeground="#ffffff",
                disabledforeground="#71717a",
                state=state,
                command=lambda selected=item: self._selected(selected),
            )
            button.pack(fill="x", ipady=4)
            if item.actionable:
                button.bind(
                    "<Enter>",
                    lambda _event, selected=item, row=button: self._row_enter(
                        selected, row
                    ),
                    add="+",
                )
                button.bind("<Leave>", self._row_leave, add="+")

    def _row_enter(self, item: PickerItem, row: tk.Misc) -> None:
        self._cancel_hide()
        if not item.actionable:
            return
        self._show_actions(item, row)

    def _row_leave(self, _event=None) -> None:
        self.owner.after(self.ACTION_GRACE_MS, self._maybe_hide_actions)

    def _maybe_hide_actions(self) -> None:
        if not self._hover.actions:
            self._hide_actions()

    def _show_actions(self, item: PickerItem, row: tk.Misc) -> None:
        self._hide_actions()
        self._action_item = item
        popup = tk.Toplevel(self.owner)
        self._action_window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg="#18181b")
        popup.bind("<Enter>", self._actions_enter, add="+")
        popup.bind("<Leave>", self._actions_leave, add="+")
        try:
            popup.wm_attributes("-toolwindow", True)
        except Exception:
            pass
        x = row.winfo_rootx() + row.winfo_width() + 4
        y = row.winfo_rooty()
        popup.geometry(f"110x38+{x}+{y}")
        button = tk.Button(
            popup,
            text=action_for_item(item),
            anchor="center",
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#f4f4f5",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            command=self._selected_action,
        )
        button.pack(fill="both", expand=True, padx=4, pady=4)

    def _selected_action(self) -> None:
        item = self._action_item
        self._hide_actions()
        if item is not None:
            self._selected(item)

    def _hide_actions(self) -> None:
        popup = self._action_window
        self._action_window = None
        self._action_item = None
        self._hover.leave_actions()
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass

    def _selected(self, item: PickerItem) -> None:
        self.hide()
        self.on_select(item)

    def hide(self) -> None:
        self._cancel_show()
        self._cancel_hide()
        self._hide_actions()
        popup = self.window
        self.window = None
        self._hover.leave_popup()
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass


__all__ = [
    "BackgroundAppPicker",
    "HoverState",
    "PickerItem",
    "action_for_item",
    "to_picker_items",
]
