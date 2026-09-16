"""Hover picker for visible background applications.

The picker is intentionally process-level: it never displays window titles,
chat names, or message content. Supported applications expose a capability
from the centralized adapter registry; everything else remains discovery-only.
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .app_adapters import adapter_for_process
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


def to_picker_items(windows: Sequence[BackgroundWindow]) -> tuple[PickerItem, ...]:
    """Convert catalog entries into title-free picker rows."""
    items = []
    for item in windows:
        spec = adapter_for_process(item.process_name)
        actionable = bool(
            spec and spec.implemented and spec.supports_background_type
        )
        items.append(
            PickerItem(
                hwnd=item.hwnd,
                pid=item.pid,
                label=spec.label if spec else _LABELS.get(
                    item.process_name,
                    item.label.removesuffix(".exe").title(),
                ),
                actionable=actionable,
                foreground=item.foreground,
                process_name=item.process_name,
                adapter_key=spec.key if actionable else "",
            )
        )
    return tuple(items)


def action_for_item(item: PickerItem) -> str:
    """Return the safe action exposed when hovering an application row."""
    spec = adapter_for_process(item.process_name)
    if not item.actionable or not spec or not spec.implemented:
        return "Preview"
    if not spec.supports_background_type:
        return "Preview"
    return spec.action


class BackgroundAppPicker:
    """Small hover popup that never foregrounds the selected target app."""

    HOVER_DELAY_MS = 140
    WIDTH = 210
    ROW_HEIGHT = 30

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[BackgroundWindow]],
        on_select: Callable[[PickerItem], None],
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.window: Optional[tk.Toplevel] = None
        self._show_job = None
        self._hide_job = None
        self._action_window: Optional[tk.Toplevel] = None
        self._action_item: Optional[PickerItem] = None
        self._inside_owner = False
        self._inside_popup = False
        self._inside_actions = False

    def bind(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", self._owner_enter, add="+")
        widget.bind("<Leave>", self._owner_leave, add="+")

    def _owner_enter(self, _event=None) -> None:
        self._inside_owner = True
        self._cancel_show()
        self._cancel_hide()
        self._show_job = self.owner.after(self.HOVER_DELAY_MS, self.show)

    def _owner_leave(self, _event=None) -> None:
        self._inside_owner = False
        self._schedule_hide()

    def _popup_enter(self, _event=None) -> None:
        self._inside_popup = True
        self._cancel_hide()

    def _popup_leave(self, _event=None) -> None:
        self._inside_popup = False
        self._schedule_hide()

    def _actions_enter(self, _event=None) -> None:
        self._inside_actions = True
        self._cancel_hide()

    def _actions_leave(self, _event=None) -> None:
        self._inside_actions = False
        self._schedule_hide()

    def _schedule_hide(self) -> None:
        self._cancel_show()
        self._cancel_hide()
        self._hide_job = self.owner.after(140, self._maybe_hide)

    def _maybe_hide(self) -> None:
        self._hide_job = None
        if not self._inside_owner and not self._inside_popup and not self._inside_actions:
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

    def show(self) -> None:
        self._show_job = None
        if not self._inside_owner:
            return
        try:
            windows = self.refresh()
        except Exception:
            windows = ()
        items = to_picker_items(windows)
        if not items:
            self.hide()
            return

        self.hide()
        self._inside_owner = True
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
        visible_items = items[:6]
        height = len(visible_items) * self.ROW_HEIGHT + 8
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        popup.bind("<Enter>", self._popup_enter, add="+")
        popup.bind("<Leave>", self._popup_leave, add="+")

        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        for item in visible_items:
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
        self.owner.after(90, self._maybe_hide_actions)

    def _maybe_hide_actions(self) -> None:
        if not self._inside_actions:
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
        self._inside_actions = False
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
        self._inside_popup = False
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass


__all__ = ["BackgroundAppPicker", "PickerItem", "action_for_item", "to_picker_items"]
