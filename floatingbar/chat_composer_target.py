"""Dedicated structural target for chat/composer applications.

The chat adapter intentionally does not identify conversations or read any
message/value content. It prefers a composer-shaped Edit/Document control when
multiple editable fields exist, so a focused search/navigation field does not
win merely because it owns focus.
"""

import time

from .app_verification import is_chat_compose_verification, verification_proof_kind
from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate
from .conversation_rows import refresh_conversation, selected_conversation_for_scope
from .evidence import EvidenceState, EvidenceStrategy, SubmissionEvidence
from . import winapi


_VERIFY_ATTEMPTS = 10
_VERIFY_INTERVAL_S = 0.1


class ChatComposerTarget(BackgroundTypingTarget):
    """Fail-closed background composer target shared by chat applications."""

    def __init__(self, hwnd: int = 0, pid: int = 0):
        super().__init__(hwnd, pid)
        self._conversation_guard = None

    def bind(self, hwnd: int, pid: int, spec=None):
        scope = super().bind(hwnd, pid, spec=spec)
        self._conversation_guard = selected_conversation_for_scope(hwnd, pid)
        return scope

    def release(self) -> None:
        self._conversation_guard = None
        super().release()

    @staticmethod
    def _is_composer(candidate) -> bool:
        return candidate.control_type in {"Edit", "Document"}

    @staticmethod
    def _is_composer_shaped(candidate) -> bool:
        return bool(getattr(candidate, "is_likely_composer_shape", False))

    def _conversation_is_still_selected(self) -> bool:
        """Require the same structurally identified row to remain selected."""
        item = self._conversation_guard
        if item is None:
            return True
        try:
            if item.hwnd != self.scope().hwnd or item.pid != self.scope().pid:
                return False
            fresh = refresh_conversation(item)
            return bool(fresh.selected)
        except Exception:
            return False

    def available(self) -> bool:
        if not super().available():
            return False
        return self._conversation_is_still_selected()

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

        # Once a composer-shaped candidate exists, non-shaped edits such as a
        # search/navigation field must not win merely because they have focus.
        # ``_composer_candidates`` already applies this preference.
        focused = next(
            (candidate for candidate in candidates if candidate.hwnd == focused_hwnd),
            None,
        )
        if focused is not None:
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

    def _verification_target(self, expected_hwnd: int = 0) -> int:
        """Revalidate the exact pinned composer before any value-length read."""
        pinned = self._pinned_hwnd
        if not pinned:
            raise RuntimeError("chat verification has no pinned composer")
        current = self._pinned_target()
        if expected_hwnd and current != expected_hwnd:
            raise RuntimeError("chat verification target changed")
        return current

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

    def _supports_compose_verification(self) -> bool:
        """Require the adapter's exact app contract, not merely a shared mode."""
        return is_chat_compose_verification(self._adapter_spec)

    def _typed_verification_result(self, strategy: str, state: EvidenceState, detail: str) -> EvidenceStrategy:
        mode = getattr(self._adapter_spec, "verification_mode", "unknown")
        evidence = SubmissionEvidence(
            state=state,
            strategy=strategy,
            detail=f"contract={mode}; {detail}",
            retryable=False,
            proof_kind=verification_proof_kind(self._adapter_spec),
        )
        return EvidenceStrategy(strategy, evidence)

    def prepare_submission_verification(self):
        if not self._supports_compose_verification():
            return None
        scope = self._scope
        if scope is None or not scope.valid:
            return None
        try:
            target = self._verification_target()
            baseline = self._composer_value_length(target)
        except Exception:
            return None
        return baseline if baseline >= 0 else None

    def begin_submission_verification(self, target_hwnd: int, state):
        if not self._supports_compose_verification():
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
        if not self._supports_compose_verification():
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
                "pinned composer changed before verification",
            )
        result = self._wait_for_length(target_hwnd, lambda length: length == 0)
        if result is True:
            try:
                self._verification_target(target_hwnd)
                if not self._conversation_is_still_selected():
                    raise RuntimeError("selected conversation changed after clear observation")
            except Exception:
                return self._typed_verification_result(
                    "posted-enter (verification-unavailable)",
                    EvidenceState.UNAVAILABLE,
                    "pinned composer or selected conversation changed after clear observation",
                )
            prefix = strategy.split(" ", 1)[0] if strategy else "posted-enter"
            return self._typed_verification_result(
                f"{prefix} (VERIFIED)",
                EvidenceState.VERIFIED,
                "exact composer observed grow then clear with stable conversation",
            )
        if result is None:
            return self._typed_verification_result(
                "posted-enter (verification-unavailable)",
                EvidenceState.UNAVAILABLE,
                "composer value became unreadable during verification",
            )
        return self._typed_verification_result(
            "posted-enter (unverified)",
            EvidenceState.SUBMITTED,
            "composer did not clear within the bounded verification window",
        )


__all__ = ["ChatComposerTarget"]
