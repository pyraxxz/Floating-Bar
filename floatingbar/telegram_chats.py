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
from .ui_identity import ancestor_identity, control_identity


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
    process_start: int | None = None

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
        try:
            process_start = winapi.get_process_creation_time(pid)
        except Exception:
            process_start = None
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
            structural_control_identity = control_identity(item.element_info)
            container_identity = ancestor_identity(item)
            key = runtime_id or (
                structural_control_identity,
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
                    control_identity=structural_control_identity,
                    container_identity=container_identity,
                    attention=_row_attention(item),
                    process_start=process_start,
                )
            )
        rows.sort(key=_row_sort_key)
        return tuple(rows[:limit])
    except Exception:
        return ()


def _same_process_instance(expected: int | None, actual: int | None) -> bool:
    """Match a saved process-start identity when both sides are observable."""
    if expected is None:
        return True
    return actual is not None and int(actual) == int(expected)


def _post_chat_click(hwnd: int, x: int, y: int, chat: TelegramChatItem) -> None:
    """Post a chat click with process-instance identity when available."""
    if chat.process_start is None:
        winapi.post_click(hwnd, x, y, expected_pid=chat.pid)
        return
    winapi.post_click(
        hwnd,
        x,
        y,
        expected_pid=chat.pid,
        expected_process_start=chat.process_start,
    )


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
    if chat.process_start is not None:
        current_process_start = winapi.get_process_creation_time(chat.pid)
        if not _same_process_instance(chat.process_start, current_process_start):
            raise RuntimeError("Telegram chat window process instance changed")
    current_rows = enumerate_telegram_chats(chat.hwnd, limit=24)

    if chat.runtime_id is not None:
        identity_matches = [row for row in current_rows if row.runtime_id == chat.runtime_id]
        if len(identity_matches) > 1:
            raise RuntimeError("Telegram chat row runtime identity is ambiguous")
        if identity_matches:
            current = identity_matches[0]
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
            if row.control_identity == chat.control_identity
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
            if row.container_identity == chat.container_identity
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


def _sole_selected_row(rows: tuple[TelegramChatItem, ...], candidate: TelegramChatItem) -> bool:
    """Require exactly one selected row in the current structural snapshot."""
    selected = tuple(row for row in rows if row.selected)
    return len(selected) == 1 and selected[0] is candidate


def chat_identity_matches(chat: TelegramChatItem) -> bool:
    """Return whether the same content-free chat identity is still selected."""
    if not chat.hwnd or not chat.pid:
        return False
    if winapi.get_window_pid(chat.hwnd) != chat.pid:
        return False
    if chat.process_start is not None:
        try:
            current_process_start = winapi.get_process_creation_time(chat.pid)
        except Exception:
            current_process_start = None
        if not _same_process_instance(chat.process_start, current_process_start):
            return False
    current_rows = enumerate_telegram_chats(chat.hwnd, limit=32)
    if chat.runtime_id is not None:
        matches = [row for row in current_rows if row.runtime_id == chat.runtime_id]
        if len(matches) == 1:
            current = matches[0]
            if chat.control_identity is not None and current.control_identity != chat.control_identity:
                return False
            return _sole_selected_row(current_rows, current)
        if len(matches) > 1:
            return False
    if chat.control_identity is not None:
        matches = [
            row
            for row in current_rows
            if row.control_identity == chat.control_identity
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
            if row.container_identity == chat.container_identity
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
    _post_chat_click(chat.hwnd, client_x, client_y, current)
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
