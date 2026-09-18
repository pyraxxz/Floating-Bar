"""Immutable target binding for one production send transaction.

TelegramTarget is deliberately allowed to discover a new window when it is
unbound. Once a send has a preferred HWND from preflight, this wrapper makes
that target sticky: if the preferred window disappears or its PID changes,
the wrapper returns an unavailable target instead of silently discovering a
different Telegram window.
"""

from typing import Any, List, Optional, Tuple

from . import winapi
from .telegram_chats import (
    TelegramChatItem,
    chat_identity_matches,
    clear_confirmed_telegram_chat_for_scope,
    confirmed_telegram_chat_for_scope,
)
from .target import TelegramNotFound, TelegramTarget
from .transaction import SendCandidate, TargetScope


class BoundTelegramTarget:
    """Telegram target facade that can hold one exact HWND/PID lease."""

    def __init__(self, target: Optional[TelegramTarget] = None):
        self._inner = target or TelegramTarget()
        self._bound_scope: Optional[TargetScope] = None
        self._bound_process_start: Optional[int] = None
        self._chat_identity: Optional[TelegramChatItem] = None

    @property
    def bound_scope(self) -> Optional[TargetScope]:
        return self._bound_scope

    @property
    def bound_process_start(self) -> Optional[int]:
        """Return the saved process-instance identity for the current lease."""
        return self._bound_process_start

    def release(self) -> None:
        """Release the transaction binding and its session-only chat confirmation."""
        bound = self._bound_scope
        chat = self._chat_identity
        if bound is not None:
            clear_confirmed_telegram_chat_for_scope(bound.hwnd, bound.pid)
        elif chat is not None:
            clear_confirmed_telegram_chat_for_scope(chat.hwnd, chat.pid)
        self._bound_scope = None
        self._bound_process_start = None
        self._chat_identity = None

    def bind_chat_identity(self, chat: Optional[TelegramChatItem]) -> None:
        """Remember the exact confirmed chat row for send-time checks.

        The picker may hand us the row it displayed before the click.
        Prefer the row recorded by ``select_telegram_chat`` after Telegram
        confirmed the background selection, while retaining the caller's row
        when no confirmed row is available.
        """
        if chat is None:
            self._chat_identity = None
            return
        try:
            confirmed = confirmed_telegram_chat_for_scope(chat.hwnd, chat.pid)
        except Exception:
            confirmed = None
        self._chat_identity = confirmed or chat

    def chat_identity_matches(self) -> bool:
        """Return whether the same remembered chat is still selected in Telegram."""
        chat = self._chat_identity
        if chat is None:
            return True
        return chat_identity_matches(chat)

    def _raw_scope(
        self,
        scope: TargetScope,
        expected_process_start: Optional[int] = None,
    ) -> bool:
        if not scope.valid:
            return False
        try:
            if not winapi.user32.IsWindow(scope.hwnd):
                return False
            if winapi.get_window_pid(scope.hwnd) != scope.pid:
                return False
            if expected_process_start is not None:
                current_process_start = winapi.get_process_creation_time(scope.pid)
                if current_process_start is None:
                    return False
                if current_process_start != expected_process_start:
                    return False
            return True
        except Exception:
            return False

    def _validate_bound(self) -> TargetScope:
        scope = self._bound_scope
        if scope is None:
            return TargetScope(0, 0)
        if not self._raw_scope(scope, expected_process_start=self._bound_process_start):
            return TargetScope(0, 0)
        return scope

    def _inner_cached_scope(self) -> Optional[TargetScope]:
        """Read the wrapped Telegram target's cached scope without discovery."""
        if not isinstance(self._inner, TelegramTarget):
            return None
        try:
            hwnd = int(self._inner.__dict__.get("_hwnd") or 0)
            pid = int(self._inner.__dict__.get("_pid") or 0)
        except Exception:
            return None
        return TargetScope(hwnd, pid) if hwnd and pid else TargetScope(0, 0)

    def _ensure_inner_aligned(self) -> None:
        """Keep Telegram UIA state on the leased scope, failing closed on drift."""
        bound = self._validate_bound()
        if not bound.valid:
            raise TelegramNotFound(
                "The original Telegram target window is no longer available."
            )

        cached = self._inner_cached_scope()
        if cached is not None and cached == bound:
            return

        selected = self._inner.select_for_send(preferred_hwnd=bound.hwnd)
        if selected != bound.hwnd:
            raise TelegramNotFound(
                "The original Telegram target could not be retained safely."
            )
        cached = self._inner_cached_scope()
        if cached is not None and cached != bound:
            raise TelegramNotFound(
                "Telegram's target process changed during the send."
            )

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

    def select_for_send(
        self,
        preferred_hwnd: int = 0,
        expected_process_start: Optional[int] = None,
    ) -> int:
        """Select or retain a Telegram window, optionally requiring one exact process instance."""
        if self._bound_scope is not None:
            bound = self._validate_bound()
            if not bound.valid:
                return 0
            if preferred_hwnd and preferred_hwnd != bound.hwnd:
                return 0
            if expected_process_start is not None:
                if (
                    self._bound_process_start is None
                    or int(self._bound_process_start) != int(expected_process_start)
                ):
                    return 0
            return bound.hwnd

        selected = self._inner.select_for_send(preferred_hwnd=preferred_hwnd)
        if not selected:
            return 0

        if preferred_hwnd:
            if selected != preferred_hwnd:
                return 0
            pid = self._inner.scope().pid
            candidate = TargetScope(selected, pid)
            if not self._raw_scope(candidate, expected_process_start=expected_process_start):
                return 0
            try:
                process_start = winapi.get_process_creation_time(candidate.pid)
            except Exception:
                process_start = None
            if expected_process_start is not None:
                if process_start is None or int(process_start) != int(expected_process_start):
                    return 0
            self._bound_process_start = process_start
            self._bound_scope = candidate
        return selected

    def compose_box(self) -> Any:
        self._ensure_inner_aligned()
        value = self._inner.compose_box()
        self._ensure_inner_aligned()
        return value

    def compose_click_point(self, compose_box: Any) -> Optional[Tuple[int, int]]:
        self._ensure_inner_aligned()
        point = self._inner.compose_click_point(compose_box)
        self._ensure_inner_aligned()
        return point

    def edit_audit(self) -> Tuple[Optional[Any], List[Tuple[Any, str]]]:
        self._ensure_inner_aligned()
        result = self._inner.edit_audit()
        self._ensure_inner_aligned()
        return result

    def remember_compose(self, edit: Any) -> None:
        self._ensure_inner_aligned()
        self._inner.remember_compose(edit)
        self._ensure_inner_aligned()

    def send_button_click(self, near_box: Any = None) -> Optional[SendCandidate]:
        self._ensure_inner_aligned()
        result = self._inner.send_button_click(near_box=near_box)
        self._ensure_inner_aligned()
        return result

    def refresh(self, preferred_hwnd: int = 0) -> None:
        """Refresh discovery only while unbound; bound targets cannot retarget."""
        if self._bound_scope is not None:
            if preferred_hwnd and preferred_hwnd != self._bound_scope.hwnd:
                return
            return
        self._inner.refresh(preferred_hwnd=preferred_hwnd)

    def _ensure_bound_for_operation(self) -> None:
        """Compatibility alias for older callers expecting the previous guard."""
        self._ensure_inner_aligned()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


__all__ = ["BoundTelegramTarget"]
