"""Prepare one guarded background-send transaction.

This module owns orchestration only: read-only preflight, exact target lease
binding, context adoption, scope validation, and immutable SendAttempt
construction. It deliberately does not inject text, touch focus, or update UI.
"""

from dataclasses import dataclass
from typing import Optional

from . import trace
from .context import capture
from .preflight import PreflightResult, run as run_preflight
from .target_contract import BackgroundTarget
from .transaction import SendAttempt, SendRequest, TargetScope


class TransactionRejected(Exception):
    """A send transaction could not be prepared safely."""

    def __init__(self, message: str, preflight: Optional[PreflightResult] = None):
        super().__init__(message)
        self.preflight = preflight


@dataclass(frozen=True)
class PreparedTransaction:
    """Immutable send attempt paired with the preflight that authorized it."""

    attempt: SendAttempt
    preflight: PreflightResult


class SendTransactionCoordinator:
    """Turn a requested send into one exact, context-guarded transaction."""

    def __init__(self, target: BackgroundTarget):
        self.target = target

    def _release_after_rejection(self) -> None:
        """Release a partially acquired target lease, when the target supports it."""
        release = getattr(self.target, "release", None)
        if callable(release):
            try:
                release()
            except Exception as exc:
                trace.trace(f"transaction: lease release after rejection failed: {exc}")

    def prepare_request(
        self,
        request: SendRequest,
        preferred_hwnd: int = 0,
    ) -> PreparedTransaction:
        """Prepare one immutable request without unpacking its state at the call site."""
        if not isinstance(request, SendRequest) or not request.valid:
            raise TransactionRejected("The send request is invalid.")
        return self.prepare(
            text=request.text,
            attempt_id=request.attempt_id,
            preferred_hwnd=preferred_hwnd,
            restore_hwnd=request.restore_hwnd,
        )

    def prepare(
        self,
        text: str,
        attempt_id: int,
        preferred_hwnd: int = 0,
        restore_hwnd: int = 0,
    ) -> PreparedTransaction:
        """Run preflight and bind the exact target without performing I/O side effects."""
        if not isinstance(attempt_id, int) or isinstance(attempt_id, bool) or attempt_id <= 0:
            raise TransactionRejected("The send attempt id is invalid.")
        if not (text or "").strip():
            raise TransactionRejected("The send text is empty.")

        try:
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

            if preferred_hwnd and preflight.hwnd != preferred_hwnd:
                raise TransactionRejected(
                    "The preferred Telegram window disappeared or was replaced; "
                    "the send was stopped instead of retargeting another window.",
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
        except TransactionRejected:
            self._release_after_rejection()
            raise
        except Exception:
            self._release_after_rejection()
            raise


__all__ = [
    "PreparedTransaction",
    "SendTransactionCoordinator",
    "TransactionRejected",
]
