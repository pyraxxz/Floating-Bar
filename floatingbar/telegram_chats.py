"""Ephemeral, read-only Telegram chat-row catalog for the background picker.

Only user-visible chat names and screen geometry needed for an explicit click,
plus content-free UI Automation identity and attention state, are kept in
memory. Nothing from this catalog is persisted or logged.
"""

from dataclasses import dataclass
import ctypes
import ctypes.wintypes as wintypes
import time

from pywinauto import Application

from . import winapi
from .conversation_attention import AttentionState, ConversationAttention
from .telegram_attention import telegram_badge_attention


_SELECTION_CONFIRM_ATTEMPTS = 5
_SELECTION_CONFIRM_INTERVAL_S = 0.05
_SELECTED_TELEGRAM_CHATS: dict[tuple[int, int], "TelegramChatItem"] = {}
_SELECTED_TELEGRAM_CHAT_LIMIT = 16


@dataclass(frozen=True)
class TelegramChatItem:
    hwnd: int
    pid: int
    name: str
    left: int
    top: int
    right: int
    bottom: int
    selected: bool = False
    runtime_id: tuple[int, ...] | None = None
    control_identity: tuple[str, ...] | None = None
    attention: ConversationAttention = ConversationAttention()
    container_identity: tuple[str, ...] | None = None

    @property
    def center(self) -> tuple[int, int]:
        return (
            self.left + max(1, self.right - self.left) // 2,
            self.top + max(1, self.bottom - self.top) // 2,
        )

    @property
    def needs_attention(self) -> bool:
        return self.attention.actionable


def confirmed_telegram_chat_for_scope(hwnd: int, pid: int) -> TelegramChatItem | None:
    """Return the last background-selected row for one exact Telegram scope."""
    return _SELECTED_TELEGRAM_CHATS.get((int(hwnd), int(pid)))


def clear_confirmed_telegram_chat_for_scope(hwnd: int, pid: int) -> None:
    """Forget one session-only selection once its transaction scope is released."""
    _SELECTED_TELEGRAM_CHATS.pop((int(hwnd), int(pid)), None)


def _remember_confirmed_chat(chat: TelegramChatItem) -> None:
    key = (int(chat.hwnd), int(chat.pid))
    _SELECTED_TELEGRAM_CHATS[key] = chat
    while len(_SELECTED_TELEGRAM_CHATS) > _SELECTED_TELEGRAM_CHAT_LIMIT:
        oldest = next(iter(_SELECTED_TELEGRAM_CHATS))
        _SELECTED_TELEGRAM_CHATS.pop(oldest, None)


def _runtime_id(item) -> tuple[int, ...] | None:
    """Return UIA runtime identity without reading chat/message content."""
    try:
        value = getattr(item.element_info, "runtime_id", None)
    except Exception:
        return None
    if value is None:
        return None
    try:
        result = tuple(int(part) for part in value)
    except (TypeError, ValueError):
        return None
    return result or None


def _control_identity(item) -> tuple[str, ...] | None:
    """Return stable structural metadata for runtimes without runtime IDs."""
    try:
        info = item.element_info
        values = (
            getattr(info, "control_type", None),
            getattr(info, "automation_id", None),
            getattr(info, "class_name", None),
            getattr(info, "framework_id", None),
        )
    except Exception:
        return None
    normalized = tuple(str(value).strip() for value in values if value not in (None, ""))
    return normalized or None


def _ancestor_identity(item, max_depth: int = 3) -> tuple[str, ...] | None:
    """Return bounded, content-free UIA ancestor structure."""
    parts: list[str] = []
    current = item
    for depth in range(1, max(1, int(max_depth)) + 1):
        try:
            current = current.parent()
            info = current.element_info
            values = (
                getattr(info, "control_type", None),
                getattr(info, "automation_id", None),
                getattr(info, "class_name", None),
                getattr(info, "framework_id", None),
            )
        except Exception:
            break
        normalized = tuple(str(value).strip() for value in values if value not in (None, ""))
        if normalized:
            parts.extend((f"ancestor{depth}", *normalized))
    return tuple(parts) or None


def _selected(item) -> bool:
    try:
        return bool(item.is_selected())
    except Exception:
        pass
    try:
        return bool(item.iface_selection_item.CurrentIsSelected)
    except Exception:
        return False


def _row_attention(item) -> ConversationAttention:
    """Use only the app-specific structural unread detector."""
    return telegram_badge_attention(item)


def _row_sort_key(row: TelegramChatItem) -> tuple[int, int, int, int, str]:
    """Prioritize explicit unread state, then current chat, then visual order."""
    attention_rank = {
        AttentionState.UNREAD: 0,
        AttentionState.RELEVANT: 1,
        AttentionState.SELECTED: 2,
        AttentionState.UNKNOWN: 3,
    }[row.attention.state]
    return (
        attention_rank,
        0 if row.selected else 1,
        row.top,
        row.left,
        row.name.casefold(),
    )


def enumerate_telegram_chats(hwnd: int, limit: int = 6) -> tuple[TelegramChatItem, ...]:
    """Return up to ``limit`` visible left-pane Telegram chat rows."""
    if not hwnd or limit <= 0:
        return ()
    try:
        pid = winapi.get_window_pid(hwnd)
        if not pid or not winapi.user32.IsWindow(hwnd):
            return ()
        app = Application(backend="uia").connect(handle=hwnd)
        window = app.window(handle=hwnd).wrapper_object()
        window_rect = window.rectangle()
        cutoff = window_rect.left + int(max(1, window_rect.width()) * 0.60)
        rows = []
        seen = set()
        for item in window.descendants(control_type="ListItem"):
            try:
                rect = item.rectangle()
                name = (item.element_info.name or "").strip()
            except Exception:
                continue
            if not name or rect.width() <= 80 or rect.height() <= 18:
                continue
            if rect.left >= cutoff or rect.top < window_rect.top or rect.bottom > window_rect.bottom:
                continue
            runtime_id = _runtime_id(item)
            control_identity = _control_identity(item)
            container_identity = _ancestor_identity(item)
            key = runtime_id or (
                control_identity,
                name.casefold(),
                rect.left,
                rect.top,
                rect.right,
                rect.bottom,
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                TelegramChatItem(
                    hwnd=hwnd,
                    pid=pid,
                    name=name,
                    left=rect.left,
                    top=rect.top,
                    right=rect.right,
                    bottom=rect.bottom,
                    selected=_selected(item),
                    runtime_id=runtime_id,
                    control_identity=control_identity,
                    container_identity=container_identity,
                    attention=_row_attention(item),
                )
            )
        rows.sort(key=_row_sort_key)
        return tuple(rows[:limit])
    except Exception:
        return ()


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = wintypes.POINT(int(x), int(y))
    fn = winapi.user32.ScreenToClient
    fn.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    fn.restype = wintypes.BOOL
    if not fn(hwnd, ctypes.byref(point)):
        raise RuntimeError("could not convert Telegram chat point to client coordinates")
    return int(point.x), int(point.y)


def _refresh_selected_row(chat: TelegramChatItem) -> TelegramChatItem:
    """Re-read the chat row immediately before clicking to avoid stale geometry."""
    if winapi.get_window_pid(chat.hwnd) != chat.pid:
        raise RuntimeError("Telegram chat window process changed")
    current_rows = enumerate_telegram_chats(chat.hwnd, limit=24)

    if chat.runtime_id is not None:
        identity_matches = [row for row in current_rows if row.runtime_id == chat.runtime_id]
        if len(identity_matches) > 1:
            raise RuntimeError("Telegram chat row runtime identity is ambiguous")
        if identity_matches:
            current = identity_matches[0]
            if current.name != chat.name:
                raise RuntimeError("Telegram chat row identity changed")
            if chat.control_identity is not None and current.control_identity != chat.control_identity:
                raise RuntimeError("Telegram chat row control identity changed")
            if abs(current.left - chat.left) + abs(current.top - chat.top) > 24:
                raise RuntimeError("Telegram chat row moved before selection")
            return current
        if chat.control_identity is None:
            raise RuntimeError("Telegram chat row runtime identity disappeared")

    if chat.control_identity is not None:
        structural_matches = [
            row
            for row in current_rows
            if row.control_identity == chat.control_identity and row.name == chat.name
        ]
        if chat.container_identity is not None:
            structural_matches = [
                row for row in structural_matches
                if row.container_identity == chat.container_identity
            ]
        if len(structural_matches) == 1:
            current = structural_matches[0]
            if abs(current.left - chat.left) + abs(current.top - chat.top) > 24:
                raise RuntimeError("Telegram chat row moved before selection")
            return current
        if len(structural_matches) > 1:
            raise RuntimeError("Telegram chat row structural identity is ambiguous")
        raise RuntimeError("Telegram chat row structural identity disappeared")

    if chat.container_identity is not None:
        container_matches = [
            row
            for row in current_rows
            if row.container_identity == chat.container_identity and row.name == chat.name
        ]
        if len(container_matches) == 1:
            current = container_matches[0]
            if abs(current.left - chat.left) + abs(current.top - chat.top) > 24:
                raise RuntimeError("Telegram chat row moved before selection")
            return current
        if len(container_matches) > 1:
            raise RuntimeError("Telegram chat row container identity is ambiguous")
        raise RuntimeError("Telegram chat row container identity disappeared")

    candidates = [row for row in current_rows if row.name == chat.name]
    if not candidates:
        raise RuntimeError("Telegram chat row is no longer available")
    if len(candidates) > 1:
        raise RuntimeError("Telegram chat row name is ambiguous")

    current = candidates[0]
    distance = abs(current.left - chat.left) + abs(current.top - chat.top)
    if distance > 24:
        raise RuntimeError("Telegram chat row moved before selection")
    return current


def _confirm_selected(chat: TelegramChatItem) -> TelegramChatItem:
    """Wait briefly for Telegram to expose the clicked row as selected."""
    last = chat
    for attempt in range(_SELECTION_CONFIRM_ATTEMPTS):
        last = _refresh_selected_row(chat)
        if last.selected:
            return last
        if attempt < _SELECTION_CONFIRM_ATTEMPTS - 1:
            time.sleep(_SELECTION_CONFIRM_INTERVAL_S)
    raise RuntimeError("Telegram chat row was not selected after background click")


def chat_identity_matches(chat: TelegramChatItem) -> bool:
    """Return whether the same content-free chat identity is still selected."""
    if not chat.hwnd or not chat.pid:
        return False
    if winapi.get_window_pid(chat.hwnd) != chat.pid:
        return False
    current_rows = enumerate_telegram_chats(chat.hwnd, limit=32)
    if chat.runtime_id is not None:
        matches = [row for row in current_rows if row.runtime_id == chat.runtime_id]
        if len(matches) == 1:
            current = matches[0]
            if current.name != chat.name:
                return False
            if chat.control_identity is not None and current.control_identity != chat.control_identity:
                return False
            if chat.container_identity is not None and current.container_identity != chat.container_identity:
                return False
            return bool(current.selected)
        if len(matches) > 1:
            return False
    if chat.control_identity is not None:
        matches = [
            row
            for row in current_rows
            if row.control_identity == chat.control_identity and row.name == chat.name
        ]
        if chat.container_identity is not None:
            matches = [
                row for row in matches
                if row.container_identity == chat.container_identity
            ]
        if len(matches) == 1:
            return bool(matches[0].selected)
        if len(matches) > 1:
            return False
        return False
    if chat.container_identity is not None:
        matches = [
            row
            for row in current_rows
            if row.container_identity == chat.container_identity and row.name == chat.name
        ]
        if len(matches) == 1:
            return bool(matches[0].selected)
        return False
    if chat.runtime_id is not None:
        return False
    candidates = [
        row
        for row in current_rows
        if row.name == chat.name and row.selected
    ]
    if len(candidates) != 1:
        return False
    current = candidates[0]
    distance = abs(current.left - chat.left) + abs(current.top - chat.top)
    return distance <= 24


def select_telegram_chat(chat: TelegramChatItem) -> TelegramChatItem:
    """Select a chat row without foregrounding Telegram and return the confirmed row.

    The row is re-enumerated immediately before injection so a stale popup
    cannot reuse an old coordinate after Telegram scrolls or rebuilds its list.
    The post-click selection state is also confirmed before the caller can bind
    this chat for background sending.
    """
    if not chat.hwnd or not chat.pid:
        raise RuntimeError("Telegram chat target is invalid")
    if not winapi.user32.IsWindow(chat.hwnd):
        raise RuntimeError("Telegram chat window no longer exists")
    current = _refresh_selected_row(chat)
    client_x, client_y = _screen_to_client(chat.hwnd, *current.center)
    winapi.post_click(chat.hwnd, client_x, client_y)
    confirmed = _confirm_selected(current)
    _remember_confirmed_chat(confirmed)
    return confirmed


__all__ = [
    "TelegramChatItem",
    "clear_confirmed_telegram_chat_for_scope",
    "confirmed_telegram_chat_for_scope",
    "enumerate_telegram_chats",
    "chat_identity_matches",
    "select_telegram_chat",
]
