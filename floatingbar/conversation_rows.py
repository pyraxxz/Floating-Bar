"""Ephemeral conversation-row discovery for background chat selection.

Rows are discovered from UI Automation structure and user-visible names only.
Message previews/bodies are never read or stored. The catalog is short-lived
and every selection revalidates the row geometry, runtime identity, and process
before clicking.
"""

from dataclasses import dataclass
import ctypes
import ctypes.wintypes as wintypes
import time
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
    # Content-free ancestor metadata helps distinguish duplicate rows in
    # Teams/Discord/Slack-style nested navigation panes when runtime IDs are
    # unavailable or recycled.
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


_SELECTED_CONVERSATIONS: dict[tuple[int, int], ConversationItem] = {}
_SELECTED_CONVERSATION_LIMIT = 16
_SELECTION_CONFIRM_ATTEMPTS = 5
_SELECTION_CONFIRM_INTERVAL_S = 0.05


def selected_conversation_for_scope(hwnd: int, pid: int) -> ConversationItem | None:
    """Return the most recently selected conversation for one exact app scope."""
    return _SELECTED_CONVERSATIONS.get((int(hwnd), int(pid)))


def _remember_selected_conversation(item: ConversationItem) -> None:
    """Keep a small in-memory selection hint for send-time revalidation."""
    key = (int(item.hwnd), int(item.pid))
    _SELECTED_CONVERSATIONS[key] = item
    while len(_SELECTED_CONVERSATIONS) > _SELECTED_CONVERSATION_LIMIT:
        oldest = next(iter(_SELECTED_CONVERSATIONS))
        _SELECTED_CONVERSATIONS.pop(oldest, None)


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


def _ancestor_identity(item, max_depth: int = 3) -> tuple[str, ...] | None:
    """Return bounded, content-free UIA ancestor structure for row disambiguation."""
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
        normalized = tuple(
            str(value).strip()
            for value in values
            if value not in (None, "")
        )
        if normalized:
            parts.extend((f"ancestor{depth}", *normalized))
    return tuple(parts) or None


def _left_pane_cutoff(window_rect, fraction: float = 0.68) -> int:
    return window_rect.left + int(max(1, window_rect.width()) * fraction)


def _row_sort_key(row: ConversationItem) -> tuple[int, int, int, int, str]:
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


def _selected_compat(item) -> bool:
    """Keep the legacy selected flag available to callers and tests."""
    try:
        return bool(item.is_selected())
    except Exception:
        try:
            return bool(item.iface_selection_item.CurrentIsSelected)
        except Exception:
            return False


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
                container_identity = _ancestor_identity(item)
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
                        selected=_selected_compat(item),
                        runtime_id=runtime_id,
                        control_identity=control_identity,
                        attention=attention,
                        container_identity=container_identity,
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
        raise RuntimeError("could not convert conversation point to client coordinates")
    return int(point.x), int(point.y)


def refresh_conversation(item: ConversationItem) -> ConversationItem:
    """Revalidate one conversation row without selecting it or reading content."""
    if winapi.get_window_pid(item.hwnd) != item.pid:
        raise RuntimeError("conversation window process changed")
    current = enumerate_conversations(item.hwnd, limit=32)

    if item.runtime_id is not None:
        identity_matches = [row for row in current if row.runtime_id == item.runtime_id]
        if len(identity_matches) > 1:
            raise RuntimeError("conversation row runtime identity is ambiguous")
        if identity_matches:
            fresh = identity_matches[0]
            if fresh.name != item.name:
                raise RuntimeError("conversation row identity changed")
            if item.control_identity is not None and fresh.control_identity != item.control_identity:
                raise RuntimeError("conversation row control identity changed")
            if abs(fresh.left - item.left) + abs(fresh.top - item.top) > 24:
                raise RuntimeError("conversation row moved before selection")
            return fresh
        if item.control_identity is None:
            raise RuntimeError("conversation row runtime identity disappeared")

    if item.control_identity is not None:
        structural_matches = [
            row for row in current
            if row.control_identity == item.control_identity and row.name == item.name
        ]
        if item.container_identity is not None:
            structural_matches = [
                row for row in structural_matches
                if row.container_identity == item.container_identity
            ]
        if len(structural_matches) == 1:
            fresh = structural_matches[0]
            if abs(fresh.left - item.left) + abs(fresh.top - item.top) > 24:
                raise RuntimeError("conversation row moved before selection")
            return fresh
        if len(structural_matches) > 1:
            raise RuntimeError("conversation row structural identity is ambiguous")
        raise RuntimeError("conversation row structural identity disappeared")

    if item.container_identity is not None:
        structural_matches = [
            row for row in current
            if row.container_identity == item.container_identity and row.name == item.name
        ]
        if len(structural_matches) == 1:
            fresh = structural_matches[0]
            if abs(fresh.left - item.left) + abs(fresh.top - item.top) > 24:
                raise RuntimeError("conversation row moved before selection")
            return fresh
        if len(structural_matches) > 1:
            raise RuntimeError("conversation row container identity is ambiguous")
        raise RuntimeError("conversation row container identity disappeared")

    candidates = [row for row in current if row.name == item.name]
    if not candidates:
        raise RuntimeError("conversation row is no longer available")
    if len(candidates) > 1:
        raise RuntimeError("conversation row name is ambiguous")

    fresh = candidates[0]
    distance = abs(fresh.left - item.left) + abs(fresh.top - item.top)
    if distance > 24:
        raise RuntimeError("conversation row moved before selection")
    return fresh


# Preserve the historical private helper for existing diagnostics/tests while
# exposing the clearer public name to new callers.
def _refresh_row(item: ConversationItem) -> ConversationItem:
    return refresh_conversation(item)


def _confirm_selected(item: ConversationItem) -> ConversationItem:
    """Wait briefly for the background click to be reflected as selected."""
    last = item
    for attempt in range(_SELECTION_CONFIRM_ATTEMPTS):
        last = refresh_conversation(item)
        if last.selected:
            return last
        if attempt < _SELECTION_CONFIRM_ATTEMPTS - 1:
            time.sleep(_SELECTION_CONFIRM_INTERVAL_S)
    raise RuntimeError("conversation row was not selected after background click")


def select_conversation(item: ConversationItem) -> ConversationItem:
    """Select a conversation and return the freshly confirmed row identity."""
    if not item.hwnd or not item.pid:
        raise RuntimeError("conversation target is invalid")
    if not winapi.user32.IsWindow(item.hwnd):
        raise RuntimeError("conversation window no longer exists")
    fresh = refresh_conversation(item)
    client_x, client_y = _screen_to_client(item.hwnd, *fresh.center)
    winapi.post_click(item.hwnd, client_x, client_y, expected_pid=item.pid)
    confirmed = _confirm_selected(fresh)
    _remember_selected_conversation(confirmed)
    return confirmed


__all__ = [
    "ConversationItem",
    "enumerate_conversations",
    "refresh_conversation",
    "selected_conversation_for_scope",
    "select_conversation",
]
