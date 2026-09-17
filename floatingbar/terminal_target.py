"""Terminal-specific background typing target.

Windows Terminal and classic console hosts are treated more strictly than the
generic adapter: the target must be a content-free structurally discovered
editable control. When several editable controls exist, a discovered
candidate is preferred over an unrelated focused field.

When a terminal control exposes a readable UI Automation ValuePattern, the
adapter can also verify that the exact pinned input accepted the injected line
and cleared after Enter. Only the value length is observed; command content
is never retained, logged, or compared. A missing ValuePattern remains a safe
``verification-unavailable`` outcome rather than an execution claim.
"""

import time

from .app_verification import is_terminal_input_verification
from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate
from .evidence import EvidenceState, EvidenceStrategy, SubmissionEvidence
from . import winapi


_VERIFY_ATTEMPTS = 10
_VERIFY_INTERVAL_S = 0.1


class TerminalTypingTarget(BackgroundTypingTarget):
    """Fail-closed target for Windows Terminal/console-host style windows."""

    def _terminal_candidates(self):
        return tuple(self.input_candidates())

    def _is_terminal_control(self, hwnd: int) -> bool:
        return any(candidate.hwnd == hwnd for candidate in self._terminal_candidates())

    def _focused_target(self) -> int:
        """Choose a discovered terminal control without requiring foreground focus."""
        candidates = self._terminal_candidates()
        if not candidates:
            raise RuntimeError("terminal target has no discovered editable target")

        scope = self._scope
        try:
            focused_hwnd = winapi.get_focused_hwnd(scope.hwnd) if scope else 0
        except Exception:
            focused_hwnd = 0

        focused = next(
            (candidate for candidate in candidates if candidate.hwnd == focused_hwnd),
            None,
        )
        if focused is not None:
            return focused.hwnd

        preferred = best_input_candidate(candidates)
        if preferred is None:
            raise RuntimeError("terminal target has no usable discovered target")
        return preferred.hwnd

    def pin_best_input(self):
        candidates = self._terminal_candidates()
        candidate = best_input_candidate(candidates)
        if candidate is None:
            raise RuntimeError("background typing target has no discovered terminal control")
        return self._pin_candidate(candidate)

    def _pinned_target(self) -> int:
        pinned = super()._pinned_target()
        if not self._is_terminal_control(pinned):
            raise RuntimeError(
                "terminal pinned control is not a discovered editable target"
            )
        return pinned

    def _verification_target(self, expected_hwnd: int = 0) -> int:
        """Revalidate the exact pinned terminal control before a length read."""
        pinned = self._pinned_hwnd
        if not pinned:
            raise RuntimeError("terminal verification has no pinned control")
        current = self._pinned_target()
        if expected_hwnd and current != expected_hwnd:
            raise RuntimeError("terminal verification target changed")
        return current

    @staticmethod
    def _terminal_value_length(hwnd: int) -> int:
        """Read only UIA value length; never retain or log terminal content."""
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
        """Return True on predicate match, False on timeout, None if unreadable."""
        readable = False
        for attempt in range(_VERIFY_ATTEMPTS):
            length = cls._terminal_value_length(hwnd)
            if length >= 0:
                readable = True
                if predicate(length):
                    return True
            if attempt < _VERIFY_ATTEMPTS - 1:
                time.sleep(_VERIFY_INTERVAL_S)
        return False if readable else None

    def _supports_terminal_verification(self) -> bool:
        """Require the exact adapter contract before claiming terminal evidence."""
        return is_terminal_input_verification(self._adapter_spec)

    def _typed_verification_result(self, strategy: str, state: EvidenceState, detail: str) -> EvidenceStrategy:
        mode = getattr(self._adapter_spec, "verification_mode", "unknown")
        evidence = SubmissionEvidence(
            state=state,
            strategy=strategy,
            detail=f"contract={mode}; {detail}",
            retryable=False,
        )
        return EvidenceStrategy(strategy, evidence)

    def prepare_submission_verification(self):
        if not self._supports_terminal_verification():
            return None
        scope = self._scope
        if scope is None or not scope.valid:
            return None
        try:
            target = self._verification_target()
            baseline = self._terminal_value_length(target)
        except Exception:
            return None
        return baseline if baseline >= 0 else None

    def begin_submission_verification(self, target_hwnd: int, state):
        if not self._supports_terminal_verification():
            return state
        if state is None:
            return None
        try:
            target_hwnd = self._verification_target(target_hwnd)
        except Exception:
            return None
        result = self._wait_for_length(target_hwnd, lambda length: length > state)
        if result is not True:
            return None
        return state

    def finish_submission_verification(self, target_hwnd: int, state, strategy: str):
        if not self._supports_terminal_verification():
            return strategy
        if state is None:
            return self._typed_verification_result(
                "posted-enter (verification-unavailable)",
                EvidenceState.UNAVAILABLE,
                "baseline or post-injection growth was not proven",
            )
        try:
            target_hwnd = self._verification_target(target_hwnd)
        except Exception:
            return self._typed_verification_result(
                "posted-enter (verification-unavailable)",
                EvidenceState.UNAVAILABLE,
                "pinned terminal control changed before verification",
            )
        result = self._wait_for_length(target_hwnd, lambda length: length == 0)
        if result is True:
            return self._typed_verification_result(
                "posted-enter (VERIFIED)",
                EvidenceState.VERIFIED,
                "exact terminal input observed grow then clear",
            )
        if result is None:
            return self._typed_verification_result(
                "posted-enter (verification-unavailable)",
                EvidenceState.UNAVAILABLE,
                "terminal value became unreadable during verification",
            )
        return self._typed_verification_result(
            "posted-enter (unverified)",
            EvidenceState.SUBMITTED,
            "terminal input did not clear within the bounded verification window",
        )


__all__ = ["TerminalTypingTarget"]
