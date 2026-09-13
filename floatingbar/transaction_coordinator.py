"""Prepare one guarded background-send transaction.

This module owns orchestration only: read-only preflight, exact target lease
binding, context adoption, scope validation, and immutable SendAttempt
construction. It deliberately does not inject text, touch focus, or update UI.
"""

from dataclasses import dataclass

from . import trace
from .context import capture
from .preflight import PreflightResult, run as run_preflight
from .target import TelegramNotFound
from .transaction import SendAttempt, TargetScope


class TransactionRejected(Exception):
    """A send transaction could not be prepared safely."""

    def __init__(self, message: str, preflight: PreflightResult = None):
        super().__init__(message)
        self.preflight = preflight


@dataclass(frozen=True)
class PreparedTransaction:
    """Immutable send attempt paired with the preflight that authorized it."""

    attempt: SendAttempt
    preflight: PreflightResult


class SendTransactionCoordinator:
    """Turn a requested send into one exact, context-guarded transaction."""

    def __init__(self, target):
        self.target = target

    def prepare(
        self,
        text: str,
        attempt_id: int,
        preferred_hwnd: int = 0,
        restore_hwnd: int = 0,
    ) -> PreparedTransaction:
        """Run preflight and bind the exact target without performing I/O side effects."""
        preflight = run_preflight(
            self.target,
            preferred_hwnd=preferred_hwnd,
        )
        trace.trace(
            f"transaction preflight: status={preflight.status} "
            f"path={preflight.submission_path} "
            f"context_guard={preflight.context_guard_available}"
        )
        if not preflight.ready:
            reason = "; ".join(preflight.reasons)
            raise TransactionRejected(
                reason or "Telegram send preflight blocked the send.",
                preflight=preflight,
            )

        selected = self.target.select_for_send(preferred_hwnd=preflight.hwnd)
        if selected != preflight.hwnd:
            raise TransactionRejected(
                "Telegram's preflight target could not be bound safely.",
                preflight=preflight,
            )

        context = preflight.context
        if context is None:
            try:
                context = capture(preflight.hwnd)
            except Exception:
                context = None
        if context is None or context.hwnd != preflight.hwnd:
            raise TransactionRejected(
                "Telegram target identity could not be safely captured; the send was stopped.",
                preflight=preflight,
            )
        if not context.matches():
            raise TransactionRejected(
                "The Telegram conversation or target window changed while the message was being prepared.",
                preflight=preflight,
            )

        bound_scope = self.target.scope()
        target_scope = TargetScope(preflight.hwnd, preflight.pid)
        attempt = SendAttempt(
            attempt_id=attempt_id,
            text=text,
            target=target_scope,
            restore_hwnd=restore_hwnd,
            context=context,
        )
        if not attempt.valid:
            raise TransactionRejected(
                "The send transaction could not be safely constructed; the send was stopped.",
                preflight=preflight,
            )
        if bound_scope != target_scope:
            raise TransactionRejected(
                "The send transaction target lease did not match preflight; the send was stopped.",
                preflight=preflight,
            )

        return PreparedTransaction(
            attempt=attempt,
            preflight=preflight,
        )


__all__ = [
    "PreparedTransaction",
    "SendTransactionCoordinator",
    "TransactionRejected",
]
