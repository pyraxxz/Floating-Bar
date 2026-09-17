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
    recent: bool = False

    @property
    def suffix(self) -> str:
        if self.attention in {AttentionState.UNREAD, AttentionState.RELEVANT}:
            return "  Needs attention"
        if self.selected:
            return "  Current"
        if self.recent:
            return "  Recent"
        return ""


def conversation_picker_identity(item: ConversationItem) -> tuple[object, ...]:
    """Return structural row identity without reading message content."""
    return (
        item.hwnd,
        item.pid,
        item.runtime_id,
        item.control_identity,
        item.name,
        item.left,
        item.top,
        item.right,
        item.bottom,
    )


def to_conversation_picker_rows(
    conversations: Sequence[ConversationItem],
    recent_keys: Sequence[tuple[object, ...]] = (),
) -> tuple[ConversationPickerRow, ...]:
    recent = set(recent_keys)
    return tuple(
        ConversationPickerRow(
            name=item.name,
            selected=item.selected,
            attention=item.attention.state,
            conversation=item,
            recent=conversation_picker_identity(item) in recent,
        )
        for item in conversations
    )


def paginate_conversations(
    conversations: Sequence[ConversationItem],
    offset: int,
    limit: int,
) -> tuple[tuple[ConversationItem, ...], int, bool, bool]:
    """Return one bounded page and deterministic previous/next availability."""
    catalog = tuple(conversations or ())
    page_limit = max(1, int(limit))
    safe_offset = max(0, int(offset))
    if catalog and safe_offset >= len(catalog):
        safe_offset = ((len(catalog) - 1) // page_limit) * page_limit
    page = catalog[safe_offset : safe_offset + page_limit]
    return (
        page,
        safe_offset,
        safe_offset > 0,
        safe_offset + page_limit < len(catalog),
    )


class ConversationPicker:
    WIDTH = 280
    ROW_HEIGHT = 30
    HEADER_HEIGHT = 34
    FOOTER_HEIGHT = 36
    SECTION_HEIGHT = 22
    PAGE_LIMIT = 6
    CATALOG_LIMIT = 24
    MAX_RECENT = 2

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[ConversationItem]],
        on_select: Callable[[ConversationItem], None],
        title: str = "Conversations",
        recent: Optional[Callable[[], Sequence[ConversationItem]]] = None,
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.title = title
        self.recent = recent or (lambda: ())
        self.window: Optional[tk.Toplevel] = None
        self._catalog: tuple[ConversationItem, ...] = ()
        self._recent_keys: set[tuple[object, ...]] = set()
        self._offset = 0

    def set_title(self, title: str) -> None:
        """Set the content-free application label shown above conversation rows."""
        cleaned = str(title or "Conversations").strip()
        self.title = cleaned or "Conversations"

    @staticmethod
    def _merge_catalog(
        recent: Sequence[ConversationItem],
        live: Sequence[ConversationItem],
    ) -> tuple[tuple[ConversationItem, ...], set[tuple[object, ...]]]:
        recent_rows = []
        recent_keys: set[tuple[object, ...]] = set()
        for item in recent:
            key = conversation_picker_identity(item)
            if key in recent_keys:
                continue
            recent_keys.add(key)
            recent_rows.append(item)
            if len(recent_rows) >= ConversationPicker.MAX_RECENT:
                break

        merged = list(recent_rows)
        seen = set(recent_keys)
        for item in live:
            key = conversation_picker_identity(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= ConversationPicker.CATALOG_LIMIT:
                break
        return tuple(merged[: ConversationPicker.CATALOG_LIMIT]), recent_keys

    def show(self) -> None:
        """Refresh the ephemeral catalog and open it at the first page."""
        try:
            live = tuple(self.refresh() or ())
            recent = tuple(self.recent() or ())
            catalog, recent_keys = self._merge_catalog(recent, live)
        except Exception:
            return
        self._catalog = catalog
        self._recent_keys = recent_keys
        self._offset = 0
        self._show_page()

    def _show_page(self) -> None:
        self.hide()
        conversations, offset, has_previous, has_next = paginate_conversations(
            self._catalog,
            self._offset,
            self.PAGE_LIMIT,
        )
        self._offset = offset
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
        visible_recent = sum(
            1 for item in conversations
            if conversation_picker_identity(item) in self._recent_keys
        )
        visible_live = len(conversations) - visible_recent
        sections = int(visible_recent > 0) + int(visible_recent > 0 and visible_live > 0)
        height = (
            self.HEADER_HEIGHT
            + len(conversations) * self.ROW_HEIGHT
            + sections * self.SECTION_HEIGHT
            + self.FOOTER_HEIGHT
            + 8
        )
        popup.geometry(f"{self.WIDTH}x{height}+{x}+{y}")

        start = offset + 1
        end = offset + len(conversations)
        total = len(self._catalog)
        header_text = self.title
        if total > self.PAGE_LIMIT:
            header_text = f"{self.title}  ·  {start}-{end} of {total}"
        header = tk.Label(
            popup,
            text=header_text,
            anchor="w",
            bg="#18181b",
            fg="#a1a1aa",
            font=("Segoe UI", 8, "bold"),
        )
        header.pack(fill="x", padx=8, pady=(6, 0))

        frame = tk.Frame(popup, bg="#18181b", bd=0)
        frame.pack(fill="both", expand=True, padx=4, pady=(0, 2))
        current_section = None
        for row in to_conversation_picker_rows(conversations, self._recent_keys):
            section = "Recent" if row.recent else "Open conversations"
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

        footer = tk.Frame(popup, bg="#18181b", bd=0)
        footer.pack(fill="x", padx=4, pady=(0, 4))
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)
        footer.columnconfigure(2, weight=1)

        previous = tk.Button(
            footer,
            text="Previous",
            anchor="center",
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#d4d4d8",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            state="normal" if has_previous else "disabled",
            command=lambda: self._page(-1),
        )
        previous.grid(row=0, column=0, sticky="ew", padx=2, pady=2, ipady=2)

        refresh = tk.Button(
            footer,
            text="Refresh",
            anchor="center",
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#d4d4d8",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            command=self.show,
        )
        refresh.grid(row=0, column=1, sticky="ew", padx=2, pady=2, ipady=2)

        next_page = tk.Button(
            footer,
            text="Next",
            anchor="center",
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#d4d4d8",
            activebackground="#3f3f46",
            activeforeground="#ffffff",
            state="normal" if has_next else "disabled",
            command=lambda: self._page(1),
        )
        next_page.grid(row=0, column=2, sticky="ew", padx=2, pady=2, ipady=2)

    def _page(self, direction: int) -> None:
        step = self.PAGE_LIMIT * (1 if int(direction) > 0 else -1)
        self._offset = max(0, self._offset + step)
        self._show_page()

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


__all__ = [
    "ConversationPicker",
    "ConversationPickerRow",
    "conversation_picker_identity",
    "paginate_conversations",
    "to_conversation_picker_rows",
]
