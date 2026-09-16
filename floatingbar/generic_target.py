"""Fail-closed generic background typing adapter with exact control pinning.

The adapter binds one exact top-level HWND/PID scope and can only post text to a
structurally discovered editable child in that same process. Submission is
performed by the selected adapter policy, and unsupported submit modes are
rejected before any text is delivered.
"""

from dataclasses import dataclass

from . import winapi
from .adapter_submit import submit_background_target, validate_submission_mode
from .control_candidates import (
    InputCandidate,
    best_input_candidate,
    enumerate_input_candidates,
)
from .transaction import TargetScope


@dataclass(frozen=True)
class TargetProbe:
    """Content-free snapshot of generic target readiness."""

    scope: TargetScope
    available: bool
    focused_hwnd: int
    candidate_hwnds: tuple[int, ...]
    pinned_hwnd: int = 0
    reason: str = "ready"

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_hwnds)


class BackgroundTypingTarget:
    """Exact-scope adapter for common apps whose current control accepts text."""

    def __init__(self, hwnd: int = 0, pid: int = 0):
        self._scope = TargetScope(hwnd, pid) if hwnd and pid else None
        self._pinned_hwnd = 0
        self._pinned_identity = None
        self._adapter_spec = None

    def bind(self, hwnd: int, pid: int, spec=None) -> TargetScope:
        scope = TargetScope(hwnd, pid)
        self._scope = scope
        self._adapter_spec = spec
        self.clear_pinned_input()
        return scope

    def bind_adapter(self, spec) -> None:
        self._adapter_spec = spec

    def release(self) -> None:
        self._scope = None
        self._adapter_spec = None
        self.clear_pinned_input()

    def scope(self) -> TargetScope:
        if self._scope is None:
            return TargetScope(0, 0)
        return self._scope

    def scope_matches(self, hwnd: int, pid: int) -> bool:
        scope = self._scope
        return bool(scope and scope.hwnd == hwnd and scope.pid == pid and self.available())

    def available(self) -> bool:
        scope = self._scope
        if scope is None:
            return False
        if not winapi.user32.IsWindow(scope.hwnd):
            return False
        if not winapi.user32.IsWindowVisible(scope.hwnd):
            return False
        return winapi.get_window_pid(scope.hwnd) == scope.pid

    def input_candidates(self) -> tuple[InputCandidate, ...]:
        """Return content-free editable controls inside the exact target."""
        scope = self._scope
        if scope is None or not self.available():
            return ()
        return enumerate_input_candidates(scope.hwnd)

    @staticmethod
    def _candidate_identity(candidate: InputCandidate) -> tuple:
        """Return a stable, content-free identity for one discovered control."""
        return (
            int(candidate.pid),
            str(getattr(candidate, "control_type", "")),
            str(getattr(candidate, "class_name", "")),
        )

    def _pin_candidate(self, candidate: InputCandidate) -> InputCandidate:
        scope = self._scope
        if scope is None or not scope.valid:
            raise RuntimeError("background typing target is not bound")
        if candidate.pid != scope.pid:
            raise RuntimeError("background typing candidate escaped the bound process")
        self._pinned_hwnd = candidate.hwnd
        self._pinned_identity = self._candidate_identity(candidate)
        return candidate

    def pin_best_input(self) -> InputCandidate:
        """Pin one structural input for a single send transaction."""
        candidates = self.input_candidates()
        candidate = best_input_candidate(candidates)
        if candidate is None:
            raise RuntimeError("background typing target has no discovered editable control")
        return self._pin_candidate(candidate)

    def clear_pinned_input(self) -> None:
        self._pinned_hwnd = 0
        self._pinned_identity = None

    @property
    def pinned_hwnd(self) -> int:
        return self._pinned_hwnd

    def probe(self) -> TargetProbe:
        """Capture structural target state without reading control content."""
        scope = self.scope()
        available = self.available()
        if not available:
            return TargetProbe(scope, False, 0, (), self._pinned_hwnd, "unavailable")

        try:
            focused = winapi.get_focused_hwnd(scope.hwnd)
        except Exception:
            focused = 0

        try:
            candidates = self.input_candidates()
        except Exception:
            candidates = None

        if candidates is None:
            reason = "inspection-error"
            candidate_hwnds = ()
        else:
            reason = "ready" if candidates else "no-input"
            candidate_hwnds = tuple(candidate.hwnd for candidate in candidates)

        return TargetProbe(
            scope=scope,
            available=True,
            focused_hwnd=focused if focused else 0,
            candidate_hwnds=candidate_hwnds,
            pinned_hwnd=self._pinned_hwnd,
            reason=reason,
        )

    def _focused_target(self) -> int:
        scope = self._scope
        if scope is None or not self.available():
            raise RuntimeError("background typing target is unavailable")
        focused = winapi.get_focused_hwnd(scope.hwnd)
        if not focused or not winapi.user32.IsWindow(focused):
            raise RuntimeError("background typing target has no valid focused control")
        if winapi.get_window_pid(focused) != scope.pid:
            raise RuntimeError("background typing focus moved outside the bound process")
        return focused

    def _pinned_target(self) -> int:
        pinned = self._pinned_hwnd
        scope = self._scope
        if not pinned or scope is None or not self.available():
            raise RuntimeError("background typing target has no valid pinned control")
        if not winapi.user32.IsWindow(pinned):
            raise RuntimeError("background typing pinned control no longer exists")
        if winapi.get_window_pid(pinned) != scope.pid:
            raise RuntimeError("background typing pinned control escaped the bound process")
        candidates = self.input_candidates()
        match = next((candidate for candidate in candidates if candidate.hwnd == pinned), None)
        if match is None:
            raise RuntimeError("background typing pinned control is no longer editable")
        if self._pinned_identity is not None and self._candidate_identity(match) != self._pinned_identity:
            raise RuntimeError("background typing pinned control identity changed")
        return pinned

    def type_text(self, text: str) -> int:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("background typing text must be non-empty")
        if self._pinned_hwnd:
            target = self._pinned_target()
        else:
            target = self._focused_target()
        winapi.post_text(target, text)
        return target

    def send(self, text: str) -> str:
        validate_submission_mode(self._adapter_spec)
        target = self.type_text(text)
        try:
            return submit_background_target(self._adapter_spec, target)
        finally:
            self.clear_pinned_input()


__all__ = ["BackgroundTypingTarget", "TargetProbe"]
