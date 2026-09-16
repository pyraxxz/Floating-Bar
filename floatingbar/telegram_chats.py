"""Ephemeral, read-only Telegram chat-row catalog for the background picker.

Only user-visible chat names and screen geometry needed for an explicit click
are kept in memory. Nothing from this catalog is persisted or logged.
"""

from dataclasses import dataclass
import ctypes
import ctypes.wintypes as wintypes
from typing import Sequence

from pywinauto import Application

from . import winapi


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

    @property
    def center(self) -> tuple[int, int]:
        return (
            self.left + max(1, self.right - self.left) // 2,
            self.top + max(1, self.bottom - self.top) // 2,
        )


def _selected(item) -> bool:
    try:
        return bool(item.is_selected())
    except Exception:
        pass
    try:
        return bool(item.iface_selection_item.CurrentIsSelected)
    except Exception:
        return False


def _row_sort_key(row: TelegramChatItem) -> tuple[int, int, int, str]:
    """Keep the current chat visible while preserving pane order otherwise."""
    return (0 if row.selected else 1, row.top, row.left, row.name.casefold())


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
            key = (name, rect.left, rect.top, rect.right, rect.bottom)
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
    candidates = [row for row in current_rows if row.name == chat.name]
    if not candidates:
        raise RuntimeError("Telegram chat row is no longer available")

    def distance(row: TelegramChatItem) -> int:
        return abs(row.left - chat.left) + abs(row.top - chat.top)

    current = min(candidates, key=distance)
    if distance(current) > 24:
        raise RuntimeError("Telegram chat row moved before selection")
    return current


def select_telegram_chat(chat: TelegramChatItem) -> None:
    """Select a chat row without foregrounding Telegram.

    The row is re-enumerated immediately before injection so a stale popup
    cannot reuse an old coordinate after Telegram scrolls or rebuilds its list.
    """
    if not chat.hwnd or not chat.pid:
        raise RuntimeError("Telegram chat target is invalid")
    if not winapi.user32.IsWindow(chat.hwnd):
        raise RuntimeError("Telegram chat window no longer exists")
    current = _refresh_selected_row(chat)
    client_x, client_y = _screen_to_client(chat.hwnd, *current.center)
    winapi.post_click(chat.hwnd, client_x, client_y)


__all__ = ["TelegramChatItem", "enumerate_telegram_chats", "select_telegram_chat"]
