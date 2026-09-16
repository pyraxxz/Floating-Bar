"""Dedicated structural target for chat/composer applications.

The chat adapter intentionally does not identify conversations or read any
message/value content. It only accepts a focused control that was discovered
as a visible, enabled Edit/Document candidate inside the exact bound window.
"""

from .generic_target import BackgroundTypingTarget


class ChatComposerTarget(BackgroundTypingTarget):
    """Fail-closed background composer target shared by chat applications."""

    def _focused_target(self) -> int:
        focused = super()._focused_target()
        candidates = self.input_candidates()
        match = next((candidate for candidate in candidates if candidate.hwnd == focused), None)
        if match is None:
            raise RuntimeError(
                "chat focused control is not a discovered editable composer"
            )
        if match.control_type not in {"Edit", "Document"}:
            raise RuntimeError("chat focused control has an unsupported input role")
        return focused


__all__ = ["ChatComposerTarget"]
