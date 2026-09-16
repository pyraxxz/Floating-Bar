"""Fail-closed generic background typing adapter.

This adapter deliberately stays much smaller than the Telegram path: it binds
one exact top-level HWND/PID scope and can only post text/Enter to a focused
child belonging to that same process. It does not discover another window or
bring the target to the foreground.
"""

from . import winapi
from .transaction import TargetScope


class BackgroundTypingTarget:
    """Exact-scope adapter for common apps whose current control accepts text."""

    def __init__(self, hwnd: int = 0, pid: int = 0):
        self._scope = TargetScope(hwnd, pid) if hwnd and pid else None

    def bind(self, hwnd: int, pid: int) -> TargetScope:
        scope = TargetScope(hwnd, pid)
        self._scope = scope
        return scope

    def release(self) -> None:
        self._scope = None

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

    def send(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("background typing text must be non-empty")
        focused = self._focused_target()
        winapi.post_text(focused, text)
        winapi.post_enter(focused, target=focused)
        return "posted-enter (unverified)"


__all__ = ["BackgroundTypingTarget"]
