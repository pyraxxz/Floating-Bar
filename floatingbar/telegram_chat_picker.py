"""Ephemeral Telegram chat picker UI.

The popup is deliberately separate from the generic application picker. It
shows chat names only while the popup is open and delegates selection to a
background Win32 click; no Telegram window is foregrounded by the picker.
"""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .telegram_chats import TelegramChatItem


@dataclass(frozen=True)
class ChatPickerRow:
    name: str
    selected: bool
    chat: TelegramChatItem


def to_chat_picker_rows(chats: Sequence[TelegramChatItem]) -> tuple[ChatPickerRow, ...]:
    return tuple(
        ChatPickerRow(name=chat.name, selected=chat.selected, chat=chat)
        for chat in chats
    )


class TelegramChatPicker:
    WIDTH = 260
    ROW_HEIGHT = 30
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
        popup.configure(bg="#18181b")
        popup.bind("<Escape>", lambda _event: self.hide())
        popup.protocol("WM_DELETE_WINDOW", self.hide)
        try:
            popup.wm_attributes("-toolwindow", True)
        except Exception:
            pass
        x = self.owner.winfo_rootx() + self.owner.winfo_width() + 8
        y = self.owner.winfo_rooty()
        popup.geometry(f"{self.WIDTH}x{len(chats) * self.ROW_HEIGHT + 8}+{x}+{y}")
        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        for row in to_chat_picker_rows(chats):
            suffix = "  Current" if row.selected else ""
            button = tk.Button(
                frame,
                text=row.name + suffix,
                anchor="w",
                relief="flat",
                bd=0,
                bg="#18181b",
                fg="#f4f4f5",
                activebackground="#27272a",
                activeforeground="#ffffff",
                command=lambda chat=row.chat: self._selected(chat),
            )
            button.pack(fill="x", ipady=4)

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
