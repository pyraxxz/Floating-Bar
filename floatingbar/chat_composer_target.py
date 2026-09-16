"""Dedicated structural target for chat/composer applications.

The chat adapter intentionally does not identify conversations or read any
message/value content. It prefers a composer-shaped Edit/Document control when
multiple editable fields exist, so a focused search/navigation field does not
win merely because it owns focus.
"""

import time

from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate
from . import winapi


_VERIFY_ATTEMPTS = 10
_VERIFY_INTERVAL_S = 0.1


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

    @staticmethod
    def _composer_value_length(hwnd: int) -> int:
        """Read only the UIA value length; never retain or log the text itself."""
        try:
            from pywinauto import Desktop

            element = Desktop(backend="uia").window(handle=hwnd).wrapper_object()
            try:
                value = element.iface_value.CurrentValue or ""
                return len(value)
            except Exception:
                legacy = element.legacy_properties()
                if isinstance(legacy, dict):
                    return len(legacy.get("Value") or "")
        except Exception:
            pass
        return -1

    @classmethod
    def _wait_for_length(cls, hwnd: int, predicate) -> bool | None:
        """Return True when predicate matches, False on timeout, None if unreadable."""
        readable = False
        for attempt in range(_VERIFY_ATTEMPTS):
            length = cls._composer_value_length(hwnd)
            if length >= 0:
                readable = True
                if predicate(length):
                    return True
            if attempt < _VERIFY_ATTEMPTS - 1:
                time.sleep(_VERIFY_INTERVAL_S)
        return False if readable else None

    def prepare_submission_verification(self):
        if getattr(self._adapter_spec, "verification_mode", "") != "compose-clear":
            return None
        scope = self._scope
        if scope is None or not scope.valid:
            return None
        candidates = self._composer_candidates()
        candidate = next((item for item in candidates if item.hwnd == self._pinned_hwnd), None)
        if candidate is None:
            return None
        baseline = self._composer_value_length(candidate.hwnd)
        return baseline if baseline >= 0 else None

    def begin_submission_verification(self, target_hwnd: int, state):
        if getattr(self._adapter_spec, "verification_mode", "") != "compose-clear":
            return state
        if state is None:
            return None
        result = self._wait_for_length(target_hwnd, lambda length: length > state)
        if result is not True:
            return None
        return state

    def finish_submission_verification(self, target_hwnd: int, state, strategy: str) -> str:
        if getattr(self._adapter_spec, "verification_mode", "") != "compose-clear":
            return strategy
        if state is None:
            return "posted-enter (verification-unavailable)"
        result = self._wait_for_length(target_hwnd, lambda length: length == 0)
        if result is True:
            prefix = strategy.split(" ", 1)[0] if strategy else "posted-enter"
            return f"{prefix} (VERIFIED)"
        if result is None:
            return "posted-enter (verification-unavailable)"
        return "posted-enter (unverified)"


__all__ = ["ChatComposerTarget"]
