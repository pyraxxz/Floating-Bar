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
        return "No safe input"
    if not spec.supports_background_type:
        return "No safe input"
    return spec.action


class BackgroundAppPicker:
    """Small hover popup that never foregrounds the selected target app."""

    HOVER_DELAY_MS = 140
    TRANSITION_GRACE_MS = 220
    ACTION_GRACE_MS = 220
    LIVE_REFRESH_MS = 700
    WIDTH = 238
    ROW_HEIGHT = 34
    SECTION_HEIGHT = 20
    MAX_PINNED = 3
    MAX_RECENT = 2
    MAX_VISIBLE = 6
    MIN_LIVE_VISIBLE = 3

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
        self._action_hide_job = None
        self._live_refresh_job = None
        self._live_snapshot = ()
        self._row_identity_by_widget = {}
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

        live = [item for item in live_items if (item.hwnd, item.pid) not in seen]
        # Put usable targets first so actionable apps remain discoverable.
        live.sort(key=lambda item: (not item.actionable, not item.foreground))
        live_capacity = min(
            BackgroundAppPicker.MIN_LIVE_VISIBLE,
            len(live),
        )
        historical_capacity = max(
            0,
            BackgroundAppPicker.MAX_VISIBLE - live_capacity,
        )

        historical_added = 0
        for items, limit in (
            (pinned_items, BackgroundAppPicker.MAX_PINNED),
            (recent_items, BackgroundAppPicker.MAX_RECENT),
        ):
            for item in items:
                key = (item.hwnd, item.pid)
                if not item.actionable or key in seen:
                    continue
                if historical_added >= historical_capacity:
                    break
                seen.add(key)
                merged.append(item)
                historical_added += 1
                if len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                    break
            if historical_added >= historical_capacity or len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                break

        if len(merged) < BackgroundAppPicker.MAX_VISIBLE:
            for item in live:
                key = (item.hwnd, item.pid)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= BackgroundAppPicker.MAX_VISIBLE:
                    break

        return tuple(merged)

    @staticmethod
    def _item_identity_key(item: PickerItem) -> tuple:
        """Return a stable live-window identity that survives picker reordering."""
        return (
            int(item.hwnd or 0),
            int(item.pid or 0),
            item.process_start,
        )

    def _focused_row_identity(self) -> Optional[tuple]:
        """Return the focused picker row identity without relying on row text."""
        try:
            focused = self.owner.focus_get()
        except Exception:
            return None
        return self._row_identity_by_widget.get(focused)

    def show(
        self,
        *,
        preserve_popup_hover: bool = False,
        preserve_focus_key: Optional[tuple] = None,
    ) -> None:
        self._show_job = None
        preserve_popup_hover = bool(
            preserve_popup_hover
            and self.window is not None
            and self._hover.popup
            and not self._hover.owner
            and not self._hover.actions
        )
        if not self._hover.owner and not preserve_popup_hover:
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
        self._live_snapshot = self._live_snapshot_for(windows)
        if not items:
            self.hide()
            return

        was_popup_hovered = preserve_popup_hover
        self.hide()
        if was_popup_hovered:
            self._hover.enter_popup()
        else:
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
        height = (
            len(items) * self.ROW_HEIGHT
            + len(section_names) * self.SECTION_HEIGHT
            + 42
        )
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, height)
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        popup.bind("<Enter>", self._popup_enter, add="+")
        popup.bind("<Leave>", self._popup_leave, add="+")

        frame = ui_theme.frame(popup)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        ui_theme.label(
            frame,
            text="Background apps",
            muted=True,
            bold=True,
            small=True,
        ).pack(fill="x", padx=4, pady=(1, 0))
        ui_theme.label(
            frame,
            text="Hover an app for actions  ·  ↑/↓ choose  ·  Enter open",
            dim=True,
            small=True,
        ).pack(fill="x", padx=4, pady=(1, 5))
        current_section = None
        row_buttons = []
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
            self._row_identity_by_widget[button] = self._item_identity_key(item)
            if item.actionable:
                row_buttons.append(button)
                button.bind(
                    "<Enter>",
                    lambda _event, selected=item, row=button: self._row_enter(
                        selected, row
                    ),
                    add="+",
                )
                button.bind("<Leave>", self._row_leave, add="+")
        ui_theme.bind_picker_navigation(
            popup,
            row_buttons,
            on_escape=self.hide,
        )
        if preserve_focus_key is not None:
            for row in row_buttons:
                if self._row_identity_by_widget.get(row) == preserve_focus_key:
                    try:
                        row.focus_set()
                    except Exception:
                        pass
                    break
        self._schedule_live_refresh()

    def _row_enter(self, item: PickerItem, row: tk.Misc) -> None:
        self._cancel_hide()
        self._cancel_action_hide()
        if not item.actionable:
            return
        self._show_actions(item, row)

    def _row_leave(self, _event=None) -> None:
        self._schedule_action_hide()

    def _cancel_live_refresh(self) -> None:
        if self._live_refresh_job is not None:
            try:
                self.owner.after_cancel(self._live_refresh_job)
            except Exception:
                pass
            self._live_refresh_job = None

    @staticmethod
    def _live_snapshot_for(windows: Sequence[BackgroundWindow]) -> tuple[tuple, ...]:
        return tuple(
            (
                item.hwnd,
                item.pid,
                item.process_start,
                item.process_name,
                item.window_class,
                item.foreground,
            )
            for item in windows
        )

    def _schedule_live_refresh(self) -> None:
        self._cancel_live_refresh()
        if self.window is None or not (self._hover.owner or self._hover.popup):
            return
        self._live_refresh_job = self.owner.after(
            self.LIVE_REFRESH_MS,
            self._refresh_open_picker,
        )

    def _refresh_open_picker(self) -> None:
        self._live_refresh_job = None
        if self.window is None or not (self._hover.owner or self._hover.popup):
            return
        try:
            windows = tuple(self.refresh() or ())
            snapshot = self._live_snapshot_for(windows)
        except Exception:
            self._schedule_live_refresh()
            return
        if snapshot != self._live_snapshot and not self._hover.actions:
            focus_key = self._focused_row_identity()
            kwargs = {}
            if self._hover.popup and not self._hover.owner:
                kwargs["preserve_popup_hover"] = True
            if focus_key is not None:
                kwargs["preserve_focus_key"] = focus_key
            self.show(**kwargs)
            return
        self._schedule_live_refresh()

    def _cancel_action_hide(self) -> None:
        if self._action_hide_job is not None:
            try:
                self.owner.after_cancel(self._action_hide_job)
            except Exception:
                pass
            self._action_hide_job = None

    def _schedule_action_hide(self) -> None:
        self._cancel_action_hide()
        self._action_hide_job = self.owner.after(
            self.ACTION_GRACE_MS,
            self._maybe_hide_actions,
        )

    def _maybe_hide_actions(self) -> None:
        if not self._hover.actions:
            self._hide_actions()

    def _show_actions(self, item: PickerItem, row: tk.Misc) -> None:
        self._cancel_action_hide()
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
        x, y = ui_theme.place_popup_near(row, popup, 132, height, gap=4)
        popup.geometry(f"132x{height}+{x}+{y}")
        action_button = ui_theme.button(
            popup,
            text=action_for_item(item),
            command=self._selected_action,
            primary=True,
        )
        action_button.pack(fill="x", padx=4, pady=(4, 2), ipady=4)
        action_rows = [action_button]
        if self.pin_toggle is not None:
            pin_button = ui_theme.button(
                popup,
                text="Unpin" if item.pinned else "Pin",
                command=self._toggle_pin,
                subtle=True,
            )
            pin_button.pack(fill="x", padx=4, pady=(2, 4), ipady=2)
            action_rows.append(pin_button)
        ui_theme.bind_picker_navigation(
            popup,
            action_rows,
            on_escape=self._hide_actions,
        )

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
        self._cancel_action_hide()
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
        self._cancel_live_refresh()
        self._cancel_action_hide()
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
