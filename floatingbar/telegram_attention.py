"""Telegram-specific, content-free conversation attention detector.

Telegram has added UI Automation accessibility for unread badge announcements in
recent Desktop builds. This detector only accepts an explicit numeric badge
signal exposed through UIA metadata. It never reads chat previews, message
bodies, or arbitrary accessible names as evidence of unread state.
"""

import re

from .conversation_attention import (
    AttentionState,
    ConversationAttention,
)


_BADGE_STATUS_RE = re.compile(r"^\s*\d{1,6}\s*$")
_UNREAD_MARKER_RE = re.compile(r"^(?:unread|new\s+messages?)$", re.IGNORECASE)


def _metadata(item):
    try:
        info = item.element_info
    except Exception:
        return ()
    values = []
    for name in (
        "item_status",
        "localized_control_type",
        "automation_id",
        "class_name",
    ):
        try:
            value = getattr(info, name, None)
        except Exception:
            value = None
        if value not in (None, ""):
            values.append((name, str(value).strip()))
    return tuple(values)


def telegram_badge_attention(item) -> ConversationAttention:
    """Detect unread only from an explicit UIA badge/status contract.

    A numeric ItemStatus is treated as a badge count. A narrowly allowlisted
    accessibility marker such as ``Unread``/``New messages`` is also accepted.
    Any arbitrary text, preview, or unknown status fails closed to UNKNOWN.
    """
    metadata = _metadata(item)
    for key, value in metadata:
        if key == "item_status" and _BADGE_STATUS_RE.fullmatch(value):
            try:
                count = int(value)
            except ValueError:
                count = 0
            if count > 0:
                return ConversationAttention(
                    AttentionState.UNREAD,
                    "telegram-uia-badge",
                )
        if key in {"item_status", "localized_control_type", "automation_id", "class_name"}:
            if _UNREAD_MARKER_RE.fullmatch(value):
                return ConversationAttention(
                    AttentionState.UNREAD,
                    "telegram-uia-marker",
                )

    return ConversationAttention()


__all__ = ["telegram_badge_attention"]
