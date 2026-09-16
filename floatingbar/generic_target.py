"""Fail-closed generic background typing adapter with exact control pinning.

The adapter binds one exact top-level HWND/PID scope and can only post text/
Enter to a structurally discovered editable child in that same process. It
does not discover another window or bring the target to the foreground.
"""

from dataclasses import dataclass

from . import winapi
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

    @property
    def candidate_count(self) -> int:
        return len(self.candidate_hwnds)


class BackgroundTypingTarget:
    """Exact-scope adapter for common apps whose current control accepts text."""

    def __init__(self, hwnd: int = 0, pid: int = 0):
        self._scope = TargetScope(hwnd, pid) if hwnd and pid else None
        self._pinned_hwnd = 0

    def bind(self, hwnd: int, pid: int) -> TargetScope:
        scope = TargetScope(hwnd, pid)
        self._scope = scope
        self._pinned_hwnd = 0
        return scope

    def release(self) -> None:
        self._scope = None
        self._pinned_hwnd = 0

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
        if winapi.is_minimized(scope.hwnd):
            return False
        return winapi.get_window_pid(scope.hwnd) == scope.pid

    def input_candidates(self) -> tuple[InputCandidate, ...]:
        """Return content-free editable controls inside the exact target."""
        scope = self._scope
        if scope is None or not self.available():
            return ()
        return enumerate_input_candidates(scope.hwnd)

    def pin_best_input(self) -> InputCandidate:
        """Pin one structural input for a single send transaction."""
        candidates = self.input_candidates()
        candidate = best_input_candidate(candidates)
        if candidate is None:
            raise RuntimeError("background typing target has no discovered editable control")
        scope = self._scope
        if scope is None or candidate.pid != scope.pid:
            raise RuntimeError("background typing candidate escaped the bound process")
        self._pinned_hwnd = candidate.hwnd
        return candidate

    def clear_pinned_input(self) -> None:
        self._pinned_hwnd = 0

    @property
    def pinned_hwnd(self) -> int:
        return self._pinned_hwnd

    def probe(self) -> TargetProbe:
        """Capture structural target state without reading control content."""
        scope = self.scope()
        available = self.available()
        if not available:
            return TargetProbe(scope, False, 0, (), self._pinned_hwnd)

        try:
            focused = winapi.get_focused_hwnd(scope.hwnd)
        except Exception:
            focused = 0

        try:
            candidates = self.input_candidates()
        except Exception:
            candidates = ()

        return TargetProbe(
            scope=scope,
            available=True,
            focused_hwnd=focused if focused else 0,
            candidate_hwnds=tuple(candidate.hwnd for candidate in candidates),
            pinned_hwnd=self._pinned_hwnd,
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
        candidates = {candidate.hwnd for candidate in self.input_candidates()}
        if pinned not in candidates:
            raise RuntimeError("background typing pinned control is no longer editable")
        return pinned

    def send(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("background typing text must be non-empty")

        if self._pinned_hwnd:
            target = self._pinned_target()
        else:
            target = self._focused_target()

        winapi.post_text(target, text)
        winapi.post_enter(target, target=target)
        self.clear_pinned_input()
        return "posted-enter (unverified)"


__all__ = ["BackgroundTypingTarget", "TargetProbe"]
