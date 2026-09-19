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
from . import ui_theme


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
    pinned: bool = False
    window_class: str = ""
    process_start: int | None = None


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
                window_class=str(getattr(item, "window_class", "") or ""),
                process_start=getattr(item, "process_start", None),
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
    WIDTH = 238
    ROW_HEIGHT = 34
    SECTION_HEIGHT = 20
    MAX_PINNED = 3
    MAX_RECENT = 2
    MAX_VISIBLE = 6

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[BackgroundWindow]],
        on_select: Callable[[PickerItem], None],
        recent: Optional[Callable[[], Sequence[PickerItem]]] = None,
        pinned: Optional[Callable[[Sequence[BackgroundWindow]], Sequence[PickerItem]]] = None,
        pin_toggle: Optional[Callable[[PickerItem], None]] = None,
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.recent = recent or (lambda: ())
        self.pinned = pinned or (lambda _windows: ())
        self.pin_toggle = pin_toggle
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
        pinned_items: Sequence[PickerItem],
        recent_items: Sequence[PickerItem],
        live_items: Sequence[PickerItem],
    ) -> tuple[PickerItem, ...]:
        """Prefer pinned identity, then recent identity, then live discovery."""
        merged = []
        seen = set()
        for items, limit in (
            (pinned_items, BackgroundAppPicker.MAX_PINNED),
            (recent_items, BackgroundAppPicker.MAX_RECENT),
        ):
            added = 0
            for item in items:
                key = (item.hwnd, item.pid)
                if not item.actionable or key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                added += 1
                if added >= limit or len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                    break
            if len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                break
        if len(merged) < BackgroundAppPicker.MAX_VISIBLE:
            for item in live_items:
                key = (item.hwnd, item.pid)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                    break
        return tuple(merged)

    def show(self) -> None:
        self._show_job = None
        if not self._hover.owner:
            return
        try:
            windows = tuple(self.refresh() or ())
        except Exception:
            windows = ()
        live_items = to_picker_items(windows)
        try:
            pinned_items = tuple(self.pinned(windows) or ())
        except Exception:
            pinned_items = ()
        try:
            recent_items = tuple(self.recent() or ())
        except Exception:
            recent_items = ()
        items = self._merge_items(pinned_items, recent_items, live_items)
        if not items:
            self.hide()
            return

        self.hide()
        self._hover.enter_owner()
        popup = tk.Toplevel(self.owner)
        self.window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        ui_theme.style_popup(popup)

        section_names = []
        for item in items:
            section = "Pinned" if item.pinned else "Recent" if item.recent else "Open apps"
            if section not in section_names:
                section_names.append(section)
        height = len(items) * self.ROW_HEIGHT + len(section_names) * self.SECTION_HEIGHT + 14
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, height)
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        popup.bind("<Enter>", self._popup_enter, add="+")
        popup.bind("<Leave>", self._popup_leave, add="+")

        frame = ui_theme.frame(popup)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        current_section = None
        for item in items:
            section = "Pinned" if item.pinned else "Recent" if item.recent else "Open apps"
            if section != current_section:
                if current_section is not None:
                    tk.Frame(frame, bg=ui_theme.BORDER, height=1).pack(fill="x", pady=3)
                tk.Label(
                    frame,
                    text=section,
                    anchor="w",
                    bg=ui_theme.SURFACE,
                    fg=ui_theme.TEXT_DIM,
                    font=ui_theme.FONT_SMALL_BOLD,
                ).pack(fill="x", padx=4, pady=(1, 2))
                current_section = section
            button = ui_theme.row_button(
                frame,
                text=f"{item.label}   ·   {action_for_item(item)}",
                disabled=not item.actionable,
                command=lambda selected=item: self._selected(selected),
            )
            button.pack(fill="x", ipady=5)
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
        ui_theme.style_popup(popup)
        popup.bind("<Enter>", self._actions_enter, add="+")
        popup.bind("<Leave>", self._actions_leave, add="+")
        x = row.winfo_rootx() + row.winfo_width() + 4
        y = row.winfo_rooty()
        height = 78 if self.pin_toggle is not None else 44
        x, y = ui_theme.place_popup_near(self.owner, popup, 132, height, gap=4)
        popup.geometry(f"132x{height}+{x}+{y}")
        action_button = ui_theme.button(
            popup,
            text=action_for_item(item),
            command=self._selected_action,
            primary=True,
        )
        action_button.pack(fill="x", padx=4, pady=(4, 2), ipady=4)
        if self.pin_toggle is not None:
            pin_button = ui_theme.button(
                popup,
                text="Unpin" if item.pinned else "Pin",
                command=self._toggle_pin,
                subtle=True,
            )
            pin_button.pack(fill="x", padx=4, pady=(2, 4), ipady=2)

    def _toggle_pin(self) -> None:
        item = self._action_item
        callback = self.pin_toggle
        self._hide_actions()
        self.hide()
        if item is not None and callback is not None:
            callback(item)

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
