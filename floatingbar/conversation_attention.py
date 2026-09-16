"""Content-free conversation attention state contracts.

Attention is deliberately separate from conversation identity. A row can be
marked selected because UI Automation exposes selection, but unread/relevant
state is only allowed when an application-specific detector supplies an
explicit structural signal. Message previews, message bodies, and text
values are never inspected by this module.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class AttentionState(str, Enum):
    UNKNOWN = "unknown"
    SELECTED = "selected"
    UNREAD = "unread"
    RELEVANT = "relevant"


@dataclass(frozen=True)
class ConversationAttention:
    state: AttentionState = AttentionState.UNKNOWN
    source: str = "none"

    @property
    def actionable(self) -> bool:
        return self.state in {AttentionState.UNREAD, AttentionState.RELEVANT}


AttentionDetector = Callable[[object], ConversationAttention]


def selected_attention(item) -> ConversationAttention:
    """Return selected state from UIA selection semantics only."""
    try:
        selected = bool(item.is_selected())
    except Exception:
        try:
            selected = bool(item.iface_selection_item.CurrentIsSelected)
        except Exception:
            selected = False
    if selected:
        return ConversationAttention(AttentionState.SELECTED, "uia-selection")
    return ConversationAttention()


def safe_detect(item, detector: Optional[AttentionDetector]) -> ConversationAttention:
    """Run an optional app-specific detector and fail closed on ambiguity."""
    if detector is None:
        return selected_attention(item)
    try:
        result = detector(item)
    except Exception:
        return ConversationAttention()
    if not isinstance(result, ConversationAttention):
        return ConversationAttention()
    return result


__all__ = [
    "AttentionDetector",
    "AttentionState",
    "ConversationAttention",
    "safe_detect",
    "selected_attention",
]
