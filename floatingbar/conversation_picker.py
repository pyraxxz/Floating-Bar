"""Ephemeral picker for background chat conversations."""

from dataclasses import dataclass
import tkinter as tk
from typing import Callable, Optional, Sequence

from .conversation_attention import AttentionState
from .conversation_rows import ConversationItem
from . import ui_theme


@dataclass(frozen=True)
class ConversationPickerRow:
    name: str
    selected: bool
    attention: AttentionState
    conversation: ConversationItem
    recent: bool = False
    pinned: bool = False

    @property
    def suffix(self) -> str:
        if self.attention in {AttentionState.UNREAD, AttentionState.RELEVANT}:
            return "  Needs attention"
        if self.selected:
            return "  Current"
        if self.pinned:
            return "  Pinned"
        if self.recent:
            return "  Recent"
        return ""


def conversation_picker_identity(item: ConversationItem) -> tuple[object, ...]:
    """Return the strongest available content-free row identity."""
    scope = (item.hwnd, item.pid)
    # Runtime identity is strongest and is independent of the visible label.
    if item.runtime_id is not None:
        return scope + ("runtime", item.runtime_id)
    # Structural identity is next. The ancestor chain disambiguates duplicate
    # row controls without relying on message text or window content.
    if item.control_identity is not None or item.container_identity is not None:
        return scope + ("structural", item.control_identity, item.container_identity)
    # Geometry is only a fallback when no stronger identity exists.
    return scope + (
        "label",
        item.name.casefold(),
        "geometry",
        item.left,
        item.top,
        item.right,
        item.bottom,
    )


def to_conversation_picker_rows(
    conversations: Sequence[ConversationItem],
    recent_keys: Sequence[tuple[object, ...]] = (),
    pinned_keys: Sequence[tuple[object, ...]] = (),
) -> tuple[ConversationPickerRow, ...]:
    recent = set(recent_keys)
    pinned = set(pinned_keys)
    return tuple(
        ConversationPickerRow(
            name=item.name,
            selected=item.selected,
            attention=item.attention.state,
            conversation=item,
            recent=conversation_picker_identity(item) in recent,
            pinned=conversation_picker_identity(item) in pinned,
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
    WIDTH = 320
    ROW_HEIGHT = 36
    HEADER_HEIGHT = 52
    FOOTER_HEIGHT = 36
    SECTION_HEIGHT = 22
    PAGE_LIMIT = 6
    CATALOG_LIMIT = 24
    MAX_PINNED = 3
    MAX_RECENT = 2

    def __init__(
        self,
        owner: tk.Misc,
        refresh: Callable[[], Sequence[ConversationItem]],
        on_select: Callable[[ConversationItem], None],
        title: str = "Conversations",
        recent: Optional[Callable[[], Sequence[ConversationItem]]] = None,
        pinned: Optional[Callable[[], Sequence[ConversationItem]]] = None,
        pin_toggle: Optional[Callable[[ConversationItem], None]] = None,
    ) -> None:
        self.owner = owner
        self.refresh = refresh
        self.on_select = on_select
        self.title = title
        self.recent = recent or (lambda: ())
        self.pinned = pinned or (lambda: ())
        self.pin_toggle = pin_toggle
        self.window: Optional[tk.Toplevel] = None
        self._catalog: tuple[ConversationItem, ...] = ()
        self._recent_keys: set[tuple[object, ...]] = set()
        self._pinned_keys: set[tuple[object, ...]] = set()
        self._offset = 0

    def set_title(self, title: str) -> None:
        """Set the content-free application label shown above conversation rows."""
        cleaned = str(title or "Conversations").strip()
        self.title = cleaned or "Conversations"

    @staticmethod
    def _merge_catalog(
        pinned: Sequence[ConversationItem],
        recent: Sequence[ConversationItem],
        live: Sequence[ConversationItem],
    ) -> tuple[
        tuple[ConversationItem, ...],
        set[tuple[object, ...]],
        set[tuple[object, ...]],
    ]:
        pinned_rows = []
        pinned_keys: set[tuple[object, ...]] = set()
        for item in pinned:
            key = conversation_picker_identity(item)
            if key in pinned_keys:
                continue
            pinned_keys.add(key)
            pinned_rows.append(item)
            if len(pinned_rows) >= ConversationPicker.MAX_PINNED:
                break

        recent_rows = []
        recent_keys: set[tuple[object, ...]] = set()
        seen = set(pinned_keys)
        for item in recent:
            key = conversation_picker_identity(item)
            if key in seen or key in recent_keys:
                continue
            recent_keys.add(key)
            recent_rows.append(item)
            seen.add(key)
            if len(recent_rows) >= ConversationPicker.MAX_RECENT:
                break

        merged = list(pinned_rows) + list(recent_rows)
        for item in live:
            key = conversation_picker_identity(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= ConversationPicker.CATALOG_LIMIT:
                break
        return tuple(merged[: ConversationPicker.CATALOG_LIMIT]), recent_keys, pinned_keys

    def show(self) -> None:
        """Refresh the ephemeral catalog and open it at the first page."""
        try:
            live = tuple(self.refresh() or ())
            pinned = tuple(self.pinned() or ())
            recent = tuple(self.recent() or ())
            catalog, recent_keys, pinned_keys = self._merge_catalog(pinned, recent, live)
        except Exception:
            return
        self._catalog = catalog
        self._recent_keys = recent_keys
        self._pinned_keys = pinned_keys
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
        ui_theme.style_popup(popup)
        popup.protocol("WM_DELETE_WINDOW", self.hide)
        
        visible_pinned = sum(
            1 for item in conversations
            if conversation_picker_identity(item) in self._pinned_keys
        )
        visible_recent = sum(
            1 for item in conversations
            if conversation_picker_identity(item) in self._recent_keys
        )
        visible_live = len(conversations) - visible_pinned - visible_recent
        sections = sum(
            1 for value in (visible_pinned, visible_recent, visible_live) if value > 0
        )
        height = (
            self.HEADER_HEIGHT
            + len(conversations) * self.ROW_HEIGHT
            + sections * self.SECTION_HEIGHT
            + self.FOOTER_HEIGHT
            + 14
        )
        x, y = ui_theme.place_popup_near(self.owner, popup, self.WIDTH, height)
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
            bg=ui_theme.SURFACE,
            fg=ui_theme.TEXT_MUTED,
            font=ui_theme.FONT_SMALL_BOLD,
        )
        header.pack(fill="x", padx=8, pady=(6, 0))
        ui_theme.label(
            popup,
            text="↑/↓ move  ·  Enter select  ·  Esc close",
            dim=True,
            small=True,
        ).pack(fill="x", padx=8, pady=(1, 2))

        frame = ui_theme.frame(popup)
        frame.pack(fill="both", expand=True, padx=4, pady=(0, 2))
        current_section = None
        row_buttons = []
        for row in to_conversation_picker_rows(
            conversations,
            self._recent_keys,
            self._pinned_keys,
        ):
            section = "Pinned" if row.pinned else "Recent" if row.recent else "Open conversations"
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
            row_frame = ui_theme.frame(frame)
            row_frame.pack(fill="x")
            row_frame.columnconfigure(0, weight=1)
            attention = row.attention in {AttentionState.UNREAD, AttentionState.RELEVANT}
            button = ui_theme.row_button(
                row_frame,
                text=row.name + row.suffix,
                selected=row.selected,
                attention=attention,
                command=lambda item=row.conversation: self._selected(item),
            )
            button.grid(row=0, column=0, sticky="ew", ipady=4)
            row_buttons.append(button)
            if self.pin_toggle is not None:
                pin_button = ui_theme.button(
                    row_frame,
                    text="★" if row.pinned else "☆",
                    command=lambda item=row.conversation: self._toggle_pin(item),
                    subtle=True,
                    width=2,
                )
                pin_button.grid(row=0, column=1, padx=(2, 0), ipady=2)

        ui_theme.bind_picker_navigation(popup, row_buttons, on_escape=self.hide)

        footer = ui_theme.frame(popup)
        footer.pack(fill="x", padx=4, pady=(0, 4))
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)
        footer.columnconfigure(2, weight=1)

        previous = ui_theme.button(
            footer,
            text="Previous",
            anchor="center",
            relief="flat",
            bd=0,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT_MUTED,
            activebackground=ui_theme.SURFACE_HOVER,
            activeforeground=ui_theme.TEXT_STRONG,
            state="normal" if has_previous else "disabled",
            command=lambda: self._page(-1),
        )
        previous.grid(row=0, column=0, sticky="ew", padx=2, pady=2, ipady=2)

        refresh = ui_theme.button(
            footer,
            text="Refresh",
            anchor="center",
            relief="flat",
            bd=0,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT_MUTED,
            activebackground=ui_theme.SURFACE_HOVER,
            activeforeground=ui_theme.TEXT_STRONG,
            command=self.show,
        )
        refresh.grid(row=0, column=1, sticky="ew", padx=2, pady=2, ipady=2)

        next_page = ui_theme.button(
            footer,
            text="Next",
            anchor="center",
            relief="flat",
            bd=0,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT_MUTED,
            activebackground=ui_theme.SURFACE_HOVER,
            activeforeground=ui_theme.TEXT_STRONG,
            state="normal" if has_next else "disabled",
            command=lambda: self._page(1),
        )
        next_page.grid(row=0, column=2, sticky="ew", padx=2, pady=2, ipady=2)

    def _page(self, direction: int) -> None:
        step = self.PAGE_LIMIT * (1 if int(direction) > 0 else -1)
        self._offset = max(0, self._offset + step)
        self._show_page()

    def _toggle_pin(self, conversation: ConversationItem) -> None:
        callback = self.pin_toggle
        self.hide()
        if callback is not None:
            callback(conversation)
        self.show()

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
