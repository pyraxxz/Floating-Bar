"""Hover picker for visible background applications.

The picker is intentionally process-level: it never displays window titles,
chat names, or message content. Telegram and a small set of common typing /
submit applications are actionable; everything else remains discovery-only.
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .background_windows import BackgroundWindow


_ACTIONABLE = {
    "telegram.exe",
    "whatsapp.exe",
    "windowsterminal.exe",
    "wt.exe",
    "cmd.exe",
    "powershell.exe",
}
_LABELS = {
    "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp",
    "windowsterminal.exe": "Terminal",
    "wt.exe": "Terminal",
    "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell",
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


def to_picker_items(windows: Sequence[BackgroundWindow]) -> tuple[PickerItem, ...]:
    """Convert catalog entries into title-free picker rows."""
    return tuple(
        PickerItem(
            hwnd=item.hwnd,
            pid=item.pid,
            label=_LABELS.get(item.process_name, item.label.removesuffix(".exe").title()),
            actionable=item.process_name in _ACTIONABLE,
            foreground=item.foreground,
            process_name=item.process_name,
        )
        for item in windows
    )


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
        self._inside_owner = False
        self._inside_popup = False

    def bind(self, widget: tk.Misc) -> None:
        widget.bind("<Enter>", self._owner_enter, add="+")
        widget.bind("<Leave>", self._owner_leave, add="+")

    def _owner_enter(self, _event=None) -> None:
        self._inside_owner = True
        self._cancel_show()
        self._show_job = self.owner.after(self.HOVER_DELAY_MS, self.show)

    def _owner_leave(self, _event=None) -> None:
        self._inside_owner = False
        self._schedule_hide()

    def _popup_enter(self, _event=None) -> None:
        self._inside_popup = True

    def _popup_leave(self, _event=None) -> None:
        self._inside_popup = False
        self._schedule_hide()

    def _schedule_hide(self) -> None:
        self._cancel_show()
        self.owner.after(120, self.hide)

    def _cancel_show(self) -> None:
        if self._show_job is not None:
            try:
                self.owner.after_cancel(self._show_job)
            except Exception:
                pass
            self._show_job = None

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
        height = min(len(items), 6) * self.ROW_HEIGHT + 8
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        popup.bind("<Enter>", self._popup_enter, add="+")
        popup.bind("<Leave>", self._popup_leave, add="+")

        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        for item in items[:6]:
            state = "normal" if item.actionable else "disabled"
            suffix = "  Type" if item.actionable else "  Preview"
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

    def _selected(self, item: PickerItem) -> None:
        self.hide()
        self.on_select(item)

    def hide(self) -> None:
        self._cancel_show()
        popup = self.window
        self.window = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass


__all__ = ["BackgroundAppPicker", "PickerItem", "to_picker_items"]
