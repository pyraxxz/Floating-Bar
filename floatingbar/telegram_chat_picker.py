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

    def show(self) -> None:
        """Refresh the ephemeral list and replace any previous popup safely."""
        self.hide()
        try:
            chats = tuple(self.refresh() or ())[: self.LIMIT]
        except Exception:
            return
        if not chats:
            return
        popup = tk.Toplevel(self.owner)
        self.window = popup
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        ui_theme.style_popup(popup)
        popup.bind("<Escape>", lambda _event: self.hide())
        popup.protocol("WM_DELETE_WINDOW", self.hide)
        total_height = len(chats) * self.ROW_HEIGHT + 56
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, total_height)
        popup.geometry(f"{self.WIDTH}x{total_height}+{x}+{y}")
        frame = ui_theme.frame(popup, padx=8, pady=7)
        ui_theme.label(frame, text="Telegram", muted=True, bold=True, small=True).pack(fill="x", pady=(0, 3))
        ui_theme.label(frame, text="Choose a chat", muted=True, small=True).pack(fill="x", pady=(0, 5))
        frame.pack(fill="both", expand=True, padx=4, pady=4)
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
