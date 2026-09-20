"""Ephemeral Telegram chat picker UI.

The popup is deliberately separate from the generic application picker. It
shows chat names only while the popup is open and delegates selection to a
background Win32 click; no Telegram window is foregrounded by the picker.
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .conversation_attention import AttentionState
from .telegram_chats import TelegramChatItem
from . import ui_theme


@dataclass(frozen=True)
class ChatPickerRow:
    name: str
    selected: bool
    chat: TelegramChatItem

    @property
    def needs_attention(self) -> bool:
        return self.chat.attention.state is AttentionState.UNREAD


def empty_state_copy(error: bool = False) -> tuple[str, str]:
    if error:
        return (
            "Telegram chats unavailable",
            "The chat list could not be read safely. You can try again.",
        )
    return (
        "No safe chats found",
        "No safe conversation rows are available right now.",
    )


def to_chat_picker_rows(chats: Sequence[TelegramChatItem]) -> tuple[ChatPickerRow, ...]:
    return tuple(
        ChatPickerRow(name=chat.name, selected=chat.selected, chat=chat)
        for chat in chats
    )


class TelegramChatPicker:
    WIDTH = 300
    ROW_HEIGHT = 36
    LIMIT = 6

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[TelegramChatItem]],
        on_select: Callable[[TelegramChatItem], None],
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.window: Optional[tk.Toplevel] = None

    def _show_empty_state(self, *, error: bool = False) -> None:
        self.hide()
        popup = tk.Toplevel(self.owner)
        self.window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        ui_theme.style_popup(popup)
        height = 142
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, height)
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")
        frame = ui_theme.frame(popup, padx=12, pady=10)
        frame.pack(fill="both", expand=True)
        title, detail = empty_state_copy(error)
        ui_theme.label(
            frame,
            text=title,
            fg=ui_theme.TEXT_STRONG,
            bold=True,
        ).pack(fill="x")
        ui_theme.label(
            frame,
            text=detail,
            muted=True,
            small=True,
            wraplength=250,
            justify="left",
        ).pack(fill="x", pady=(3, 10))
        actions = ui_theme.frame(frame, bg=ui_theme.SURFACE)
        actions.pack(fill="x")
        refresh = ui_theme.button(
            actions,
            text="Refresh",
            command=self.show,
            primary=True,
        )
        refresh.pack(side="right", padx=(4, 0))
        close = ui_theme.button(
            actions,
            text="Dismiss",
            command=self.hide,
            subtle=True,
        )
        close.pack(side="right")
        ui_theme.bind_picker_navigation(
            popup,
            [refresh, close],
            on_escape=self.hide,
        )

    def show(self) -> None:
        """Refresh the ephemeral list and replace any previous popup safely."""
        self.hide()
        refresh_failed = False
        try:
            chats = tuple(self.refresh() or ())[: self.LIMIT]
        except Exception:
            refresh_failed = True
            chats = ()
        if not chats:
            self._show_empty_state(error=refresh_failed)
            return
        popup = tk.Toplevel(self.owner)
        self.window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        ui_theme.style_popup(popup)
        popup.protocol("WM_DELETE_WINDOW", self.hide)
        attention_count = sum(1 for chat in chats if chat.attention.state is AttentionState.UNREAD)
        total_height = len(chats) * self.ROW_HEIGHT + 98
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, total_height)
        popup.geometry(f"{self.WIDTH}x{total_height}+{x}+{y}")
        frame = ui_theme.frame(popup, padx=8, pady=7)
        ui_theme.label(frame, text="Telegram", muted=True, bold=True, small=True).pack(fill="x", pady=(0, 2))
        summary = f"{len(chats)} chats"
        if attention_count:
            summary += f"  ·  {attention_count} unread"
        ui_theme.label(frame, text=summary, muted=True, small=True).pack(fill="x", pady=(0, 1))
        ui_theme.label(frame, text="↑/↓ move  ·  Enter choose  ·  Esc close", dim=True, small=True).pack(fill="x", pady=(0, 5))
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        row_buttons = []
        for row in to_chat_picker_rows(chats):
            state_suffix = []
            if row.needs_attention:
                state_suffix.append("Unread")
            if row.selected:
                state_suffix.append("Current")
            suffix = "   ·   " + " / ".join(state_suffix) if state_suffix else ""
            button = ui_theme.row_button(
                frame,
                text=row.name + suffix,
                selected=row.selected,
                attention=row.needs_attention,
                command=lambda chat=row.chat: self._selected(chat),
            )
            button.pack(fill="x", ipady=5, pady=1)
            row_buttons.append(button)

        ui_theme.bind_picker_navigation(popup, row_buttons, on_escape=self.hide)
        footer = ui_theme.frame(popup, bg=ui_theme.SURFACE)
        footer.pack(fill="x", padx=4, pady=(1, 4))
        ui_theme.button(
            footer,
            text="Refresh",
            command=self.show,
            subtle=True,
        ).pack(side="right", padx=2, pady=2)

    def _selected(self, chat: TelegramChatItem) -> None:
        self.hide()
        self.on_select(chat)

    def hide(self) -> None:
        popup = self.window
        self.window = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass


__all__ = ["ChatPickerRow", "TelegramChatPicker", "to_chat_picker_rows"]
