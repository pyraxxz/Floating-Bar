"""Immutable target binding for one production send transaction.

TelegramTarget is deliberately allowed to discover a new window when it is
unbound. Once a send has a preferred HWND from preflight, this wrapper makes
that target sticky: if the preferred window disappears or its PID changes,
the wrapper returns an unavailable target instead of silently discovering a
different Telegram window.
"""

from typing import Any, List, Optional, Tuple

from . import winapi
from .target import TelegramNotFound, TelegramTarget
from .transaction import SendCandidate, TargetScope


class BoundTelegramTarget:
    """Telegram target facade that can hold one exact HWND/PID lease."""

    def __init__(self, target: Optional[TelegramTarget] = None):
        self._inner = target or TelegramTarget()
        self._bound_scope: Optional[TargetScope] = None

    @property
    def bound_scope(self) -> Optional[TargetScope]:
        return self._bound_scope

    def release(self) -> None:
        """Release the transaction binding after a send attempt completes."""
        self._bound_scope = None

    def _raw_scope(self, scope: TargetScope) -> bool:
        if not scope.valid:
            return False
        try:
            if not winapi.user32.IsWindow(scope.hwnd):
                return False
            return winapi.get_window_pid(scope.hwnd) == scope.pid
        except Exception:
            return False

    def _validate_bound(self) -> TargetScope:
        scope = self._bound_scope
        if scope is None:
            return TargetScope(0, 0)
        if not self._raw_scope(scope):
            return TargetScope(0, 0)
        return scope

    @property
    def hwnd(self) -> int:
        """Return only the bound HWND when a transaction lease is active."""
        if self._bound_scope is not None:
            return self._validate_bound().hwnd
        return self._inner.hwnd

    def is_available(self) -> bool:
        if self._bound_scope is not None:
            return self._validate_bound().valid
        return self._inner.is_available()

    def scope(self) -> TargetScope:
        """Return the immutable bound scope while a transaction is active."""
        if self._bound_scope is not None:
            return self._validate_bound()
        return self._inner.scope()

    def scope_matches(self, hwnd: int, pid: int = 0) -> bool:
        if self._bound_scope is not None:
            bound = self._validate_bound()
            expected_pid = pid or bound.pid
            return bool(
                bound.valid and hwnd == bound.hwnd and
                expected_pid == bound.pid
            )
        return self._inner.scope_matches(hwnd, pid)

    def select_for_send(self, preferred_hwnd: int = 0) -> int:
        """Select normally while unbound; bind strictly when a preferred HWND exists."""
        if self._bound_scope is not None:
            bound = self._validate_bound()
            if not bound.valid:
                return 0
            if preferred_hwnd and preferred_hwnd != bound.hwnd:
                return 0
            return bound.hwnd

        selected = self._inner.select_for_send(preferred_hwnd=preferred_hwnd)
        if not selected:
            return 0

        if preferred_hwnd:
            # A preferred HWND is an exact transaction requirement, not a hint.
            if selected != preferred_hwnd:
                return 0
            pid = self._inner.scope().pid
            candidate = TargetScope(selected, pid)
            if not self._raw_scope(candidate):
                return 0
            self._bound_scope = candidate
        return selected

    def compose_box(self) -> Any:
        self._ensure_bound_for_operation()
        value = self._inner.compose_box()
        self._ensure_bound_for_operation()
        return value

    def compose_click_point(self, compose_box: Any) -> Optional[Tuple[int, int]]:
        self._ensure_bound_for_operation()
        point = self._inner.compose_click_point(compose_box)
        self._ensure_bound_for_operation()
        return point

    def edit_audit(self) -> Tuple[Optional[Any], List[Tuple[Any, str]]]:
        self._ensure_bound_for_operation()
        result = self._inner.edit_audit()
        self._ensure_bound_for_operation()
        return result

    def remember_compose(self, edit: Any) -> None:
        self._ensure_bound_for_operation()
        self._inner.remember_compose(edit)
        self._ensure_bound_for_operation()

    def send_button_click(self, near_box: Any = None) -> Optional[SendCandidate]:
        self._ensure_bound_for_operation()
        result = self._inner.send_button_click(near_box=near_box)
        self._ensure_bound_for_operation()
        return result

    def refresh(self, preferred_hwnd: int = 0) -> None:
        """Refresh discovery only while unbound; bound targets cannot retarget."""
        if self._bound_scope is not None:
            if preferred_hwnd and preferred_hwnd != self._bound_scope.hwnd:
                return
            return
        self._inner.refresh(preferred_hwnd=preferred_hwnd)

    def _ensure_bound_for_operation(self) -> None:
        if self._bound_scope is None:
            return
        if not self._validate_bound().valid:
            raise TelegramNotFound(
                "The original Telegram target window is no longer available."
            )
        # Keep the wrapped target's UIA state aligned with the exact lease.
        selected = self._inner.select_for_send(
            preferred_hwnd=self._bound_scope.hwnd
        )
        if selected != self._bound_scope.hwnd:
            raise TelegramNotFound(
                "The original Telegram target could not be retained safely."
            )
        if self._inner.scope() != self._bound_scope:
            raise TelegramNotFound(
                "Telegram's target process changed during the send."
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


__all__ = ["BoundTelegramTarget"]
