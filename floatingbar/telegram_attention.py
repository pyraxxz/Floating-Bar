"""Telegram-specific, content-free conversation attention detector.

Telegram has added UI Automation accessibility for unread badge announcements in
recent Desktop builds. This detector only accepts an explicit ``ItemStatus``
signal. It never reads chat previews, message bodies, or arbitrary accessible
names as evidence of unread state.
"""

import re

from .conversation_attention import AttentionState, ConversationAttention


_BADGE_STATUS_RE = re.compile(r"^\s*\d{1,6}\s*$")
_UNREAD_MARKER_RE = re.compile(r"^(?:unread|new\s+messages?)$", re.IGNORECASE)


def _item_status(item) -> str:
    """Return only the explicit UIA ItemStatus value, never control text/name."""
    try:
        value = getattr(item.element_info, "item_status", None)
    except Exception:
        return ""
    return "" if value in (None, "") else str(value).strip()


def telegram_badge_attention(item) -> ConversationAttention:
    """Detect unread only from an explicit UIA ItemStatus contract.

    A positive numeric ItemStatus is treated as an unread badge count. A
    narrowly allowlisted ``Unread``/``New messages`` ItemStatus is also
    accepted. Any other state fails closed to UNKNOWN.
    """
    status = _item_status(item)
    if _BADGE_STATUS_RE.fullmatch(status):
        try:
            count = int(status)
        except ValueError:
            count = 0
        if count > 0:
            return ConversationAttention(AttentionState.UNREAD, "telegram-uia-badge")
    if _UNREAD_MARKER_RE.fullmatch(status):
        return ConversationAttention(AttentionState.UNREAD, "telegram-uia-marker")
    return ConversationAttention()


__all__ = ["telegram_badge_attention"]
