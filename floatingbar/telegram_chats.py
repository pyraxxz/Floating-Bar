"""Ephemeral, read-only Telegram chat-row catalog for the background picker.

Only user-visible chat names and screen geometry needed for an explicit click
are kept in memory. Nothing from this catalog is persisted or logged.
"""

from dataclasses import dataclass
from typing import Sequence

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


def enumerate_telegram_chats(hwnd: int, limit: int = 6) -> tuple[TelegramChatItem, ...]:
    """Return up to ``limit`` visible left-pane Telegram chat rows."""
    if not hwnd or limit <= 0:
        return ()
    try:
        pid = winapi.get_window_pid(hwnd)
        if not pid or not winapi.user32.IsWindow(hwnd):
            return ()
        from pywinauto import Application

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
        rows.sort(key=lambda row: (row.top, row.left, row.name.casefold()))
        return tuple(rows[:limit])
    except Exception:
        return ()


def select_telegram_chat(chat: TelegramChatItem) -> None:
    """Select a chat row without foregrounding Telegram."""
    if not chat.hwnd or not chat.pid:
        raise RuntimeError("Telegram chat target is invalid")
    if not winapi.user32.IsWindow(chat.hwnd):
        raise RuntimeError("Telegram chat window no longer exists")
    if winapi.get_window_pid(chat.hwnd) != chat.pid:
        raise RuntimeError("Telegram chat window process changed")
    client_x, client_y = winapi.screen_to_client(chat.hwnd, *chat.center)
    winapi.post_click(chat.hwnd, client_x, client_y)


__all__ = ["TelegramChatItem", "enumerate_telegram_chats", "select_telegram_chat"]
