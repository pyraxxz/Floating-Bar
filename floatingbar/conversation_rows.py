"""Ephemeral conversation-row discovery for background chat selection.

Rows are discovered from UI Automation structure and user-visible names only.
Message previews/bodies are never read or stored. The catalog is short-lived
and every selection revalidates the row geometry, runtime identity, and process
before clicking.
"""

from dataclasses import dataclass
import ctypes
import ctypes.wintypes as wintypes
from typing import Optional

from . import winapi
from .conversation_attention import AttentionDetector, AttentionState, ConversationAttention, safe_detect


@dataclass(frozen=True)
class ConversationItem:
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

    @property
    def center(self) -> tuple[int, int]:
        return (
            self.left + max(1, self.right - self.left) // 2,
            self.top + max(1, self.bottom - self.top) // 2,
        )

    @property
    def needs_attention(self) -> bool:
        return self.attention.actionable


def _runtime_id(item) -> tuple[int, ...] | None:
    """Return UIA runtime identity without reading control content."""
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
    """Return stable structural UI metadata for runtimes without runtime_id."""
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


def _left_pane_cutoff(window_rect, fraction: float = 0.68) -> int:
    return window_rect.left + int(max(1, window_rect.width()) * fraction)


def _row_sort_key(row: ConversationItem) -> tuple[int, int, int, str]:
    """Prioritize proven attention, then current conversation, then pane order."""
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


def enumerate_conversations(
    hwnd: int,
    limit: int = 6,
    control_types: tuple[str, ...] = ("ListItem", "TreeItem"),
    attention_detector: Optional[AttentionDetector] = None,
) -> tuple[ConversationItem, ...]:
    """Return a short ephemeral catalog of visible left-pane conversation rows."""
    if not hwnd or limit <= 0:
        return ()
    try:
        from pywinauto import Application

        pid = winapi.get_window_pid(hwnd)
        if not pid or not winapi.user32.IsWindow(hwnd):
            return ()
        app = Application(backend="uia").connect(handle=hwnd)
        window = app.window(handle=hwnd).wrapper_object()
        window_rect = window.rectangle()
        cutoff = _left_pane_cutoff(window_rect)
        rows = []
        seen = set()
        for control_type in control_types:
            for item in window.descendants(control_type=control_type):
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
                attention = safe_detect(item, attention_detector)
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
                    ConversationItem(
                        hwnd=hwnd,
                        pid=pid,
                        name=name,
                        left=rect.left,
                        top=rect.top,
                        right=rect.right,
                        bottom=rect.bottom,
                        selected=(attention.state is AttentionState.SELECTED or not attention.actionable and _selected_compat(item)),
                        runtime_id=runtime_id,
                        control_identity=control_identity,
                        attention=attention,
                    )
                )
        rows.sort(key=_row_sort_key)
        return tuple(rows[:limit])
    except Exception:
        return ()


def _selected_compat(item) -> bool:
    """Keep the legacy selected flag available to callers and tests."""
    try:
        return bool(item.is_selected())
    except Exception:
        try:
            return bool(item.iface_selection_item.CurrentIsSelected)
        except Exception:
            return False


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = wintypes.POINT(int(x), int(y))
    fn = winapi.user32.ScreenToClient
    fn.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    fn.restype = wintypes.BOOL
    if not fn(hwnd, ctypes.byref(point)):
        raise RuntimeError("could not convert conversation point to client coordinates")
    return int(point.x), int(point.y)


def _refresh_row(item: ConversationItem) -> ConversationItem:
    if winapi.get_window_pid(item.hwnd) != item.pid:
        raise RuntimeError("conversation window process changed")
    current = enumerate_conversations(item.hwnd, limit=32)

    if item.runtime_id is not None:
        identity_matches = [row for row in current if row.runtime_id == item.runtime_id]
        if identity_matches:
            fresh = min(
                identity_matches,
                key=lambda row: abs(row.left - item.left) + abs(row.top - item.top),
            )
            if fresh.name != item.name:
                raise RuntimeError("conversation row identity changed")
            if abs(fresh.left - item.left) + abs(fresh.top - item.top) > 24:
                raise RuntimeError("conversation row moved before selection")
            return fresh

    if item.control_identity is not None:
        structural_matches = [
            row for row in current
            if row.control_identity == item.control_identity and row.name == item.name
        ]
        if len(structural_matches) == 1:
            fresh = structural_matches[0]
            if abs(fresh.left - item.left) + abs(fresh.top - item.top) > 24:
                raise RuntimeError("conversation row moved before selection")
            return fresh
        if len(structural_matches) > 1:
            raise RuntimeError("conversation row structural identity is ambiguous")

    candidates = [row for row in current if row.name == item.name]
    if not candidates:
        raise RuntimeError("conversation row is no longer available")

    def distance(row: ConversationItem) -> int:
        return abs(row.left - item.left) + abs(row.top - item.top)

    fresh = min(candidates, key=distance)
    if distance(fresh) > 24:
        raise RuntimeError("conversation row moved before selection")
    return fresh


def select_conversation(item: ConversationItem) -> None:
    """Select a conversation with a background click after immediate revalidation."""
    if not item.hwnd or not item.pid:
        raise RuntimeError("conversation target is invalid")
    if not winapi.user32.IsWindow(item.hwnd):
        raise RuntimeError("conversation window no longer exists")
    fresh = _refresh_row(item)
    client_x, client_y = _screen_to_client(item.hwnd, *fresh.center)
    winapi.post_click(item.hwnd, client_x, client_y)


__all__ = ["ConversationItem", "enumerate_conversations", "select_conversation"]
