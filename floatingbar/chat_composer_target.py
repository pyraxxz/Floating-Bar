"""Dedicated structural target for chat/composer applications.

The chat adapter intentionally does not identify conversations or read any
message/value content. It prefers a composer-shaped Edit/Document control when
multiple editable fields exist, so a focused search/navigation field does not
win merely because it owns focus.
"""

from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate
from . import winapi


class ChatComposerTarget(BackgroundTypingTarget):
    """Fail-closed background composer target shared by chat applications."""

    @staticmethod
    def _is_composer(candidate) -> bool:
        return candidate.control_type in {"Edit", "Document"}

    @staticmethod
    def _is_composer_shaped(candidate) -> bool:
        return bool(getattr(candidate, "is_likely_composer_shape", False))

    def _composer_candidates(self):
        candidates = tuple(
            candidate for candidate in self.input_candidates() if self._is_composer(candidate)
        )
        if not candidates:
            return ()
        shaped = tuple(candidate for candidate in candidates if self._is_composer_shaped(candidate))
        return shaped or candidates

    def _focused_target(self) -> int:
        """Choose a discovered composer even when another app control owns focus."""
        candidates = self._composer_candidates()
        if not candidates:
            raise RuntimeError("chat target has no discovered editable composer")

        scope = self._scope
        try:
            focused_hwnd = winapi.get_focused_hwnd(scope.hwnd) if scope else 0
        except Exception:
            focused_hwnd = 0

        focused = next(
            (candidate for candidate in candidates if candidate.hwnd == focused_hwnd),
            None,
        )
        if focused is not None and self._is_composer_shaped(focused):
            return focused.hwnd

        preferred = best_input_candidate(candidates)
        if preferred is None:
            raise RuntimeError("chat target has no usable discovered composer")
        return preferred.hwnd

    def pin_best_input(self):
        candidates = self._composer_candidates()
        candidate = best_input_candidate(candidates)
        if candidate is None:
            raise RuntimeError("background typing target has no discovered editable composer")
        return self._pin_candidate(candidate)

    def _pinned_target(self) -> int:
        pinned = super()._pinned_target()
        candidates = self._composer_candidates()
        match = next((candidate for candidate in candidates if candidate.hwnd == pinned), None)
        if match is None or not self._is_composer(match):
            raise RuntimeError("chat pinned control is not a discovered editable composer")
        return pinned


__all__ = ["ChatComposerTarget"]
