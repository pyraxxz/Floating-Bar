"""Ephemeral picker for background chat conversations."""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .conversation_attention import AttentionState
from .conversation_rows import ConversationItem


@dataclass(frozen=True)
class ConversationPickerRow:
    name: str
    selected: bool
    attention: AttentionState
    conversation: ConversationItem

    @property
    def suffix(self) -> str:
        if self.attention in {AttentionState.UNREAD, AttentionState.RELEVANT}:
            return "  Needs attention"
        if self.selected:
            return "  Current"
        return ""


def to_conversation_picker_rows(
    conversations: Sequence[ConversationItem],
) -> tuple[ConversationPickerRow, ...]:
    return tuple(
        ConversationPickerRow(
            name=item.name,
            selected=item.selected,
            attention=item.attention.state,
            conversation=item,
        )
        for item in conversations
    )


class ConversationPicker:
    WIDTH = 260
    ROW_HEIGHT = 30
    LIMIT = 6

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[ConversationItem]],
        on_select: Callable[[ConversationItem], None],
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.window: Optional[tk.Toplevel] = None

    def show(self) -> None:
        self.hide()
        try:
            conversations = tuple(self.refresh() or ())[: self.LIMIT]
        except Exception:
            return
        if not conversations:
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
        popup.geometry(f"{self.WIDTH}x{len(conversations) * self.ROW_HEIGHT + 8}+{x}+{y}")
        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        for row in to_conversation_picker_rows(conversations):
            button = tk.Button(
                frame,
                text=row.name + row.suffix,
                anchor="w",
                relief="flat",
                bd=0,
                bg="#18181b",
                fg="#f4f4f5",
                activebackground="#27272a",
                activeforeground="#ffffff",
                command=lambda item=row.conversation: self._selected(item),
            )
            button.pack(fill="x", ipady=4)

    def _selected(self, conversation: ConversationItem) -> None:
        self.hide()
        self.on_select(conversation)

    def hide(self) -> None:
        popup = self.window
        self.window = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass


__all__ = ["ConversationPicker", "ConversationPickerRow", "to_conversation_picker_rows"]
