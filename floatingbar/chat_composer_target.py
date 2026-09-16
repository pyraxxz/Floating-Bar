"""Dedicated structural target for chat/composer applications.

The chat adapter intentionally does not identify conversations or read any
message/value content. It accepts only a structurally discovered Edit/Document
control inside the exact bound window, including when that control is pinned
for a send transaction.
"""

from .generic_target import BackgroundTypingTarget


class ChatComposerTarget(BackgroundTypingTarget):
    """Fail-closed background composer target shared by chat applications."""

    @staticmethod
    def _is_composer(candidate) -> bool:
        return candidate.control_type in {"Edit", "Document"}

    def _focused_target(self) -> int:
        focused = super()._focused_target()
        candidates = self.input_candidates()
        match = next((candidate for candidate in candidates if candidate.hwnd == focused), None)
        if match is None:
            raise RuntimeError("chat focused control is not a discovered editable composer")
        if not self._is_composer(match):
            raise RuntimeError("chat focused control has an unsupported input role")
        return focused

    def _pinned_target(self) -> int:
        pinned = super()._pinned_target()
        candidates = self.input_candidates()
        match = next((candidate for candidate in candidates if candidate.hwnd == pinned), None)
        if match is None or not self._is_composer(match):
            raise RuntimeError("chat pinned control is not a discovered editable composer")
        return pinned


__all__ = ["ChatComposerTarget"]
