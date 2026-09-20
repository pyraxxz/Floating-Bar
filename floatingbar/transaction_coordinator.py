"""Prepare one guarded background-send transaction.

The coordinator owns sequencing and exact target binding. Target-specific
preflight/context rules live behind a preparation policy so the transaction
layer does not need to know Telegram, chat, or terminal UI details.
"""

from dataclasses import dataclass
from typing import Optional, Protocol

from . import trace
from .context import capture
from .preflight import PreflightResult, run as run_preflight
from .target_contract import BackgroundTarget
from .transaction import SendAttempt, SendRequest, TargetScope


class TransactionPreparationPolicy(Protocol):
    """Target-specific preparation contract used by the generic coordinator."""

    target_label: str
    requires_context: bool

    def preflight(
        self,
        target: BackgroundTarget,
        preferred_hwnd: int = 0,
    ) -> PreflightResult:
        """Run the target's read-only preparation gate."""

    def capture_context(self, hwnd: int) -> object | None:
        """Capture any non-content context guard needed after preflight."""

    def context_matches(self, context: object) -> bool:
        """Return whether the prepared context is still stable."""


@dataclass(frozen=True)
class TelegramTransactionPreparationPolicy:
    """Preserve today's Telegram preparation semantics behind the policy seam."""

    target_label: str = "Telegram"
    requires_context: bool = True

    def preflight(
        self,
        target: BackgroundTarget,
        preferred_hwnd: int = 0,
    ) -> PreflightResult:
        return run_preflight(target, preferred_hwnd=preferred_hwnd)

    def capture_context(self, hwnd: int) -> object | None:
        try:
            return capture(hwnd)
        except Exception:
            return None

    def context_matches(self, context: object) -> bool:
        try:
            return bool(context is not None and context.matches())
        except Exception:
            return False


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

    def __init__(
        self,
        target: BackgroundTarget,
        policy: TransactionPreparationPolicy | None = None,
    ):
        self.target = target
        self.policy = policy or TelegramTransactionPreparationPolicy()

    def _release_after_rejection(self) -> None:
        """Release a partially acquired target lease through the formal contract."""
        try:
            self.target.release()
        except Exception as exc:
            trace.trace_exception("transaction: lease release after rejection failed", exc)

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
            preflight = self.policy.preflight(
                self.target,
                preferred_hwnd=preferred_hwnd,
            )
            trace.trace(
                f"transaction preflight: status={preflight.status} "
                f"path={preflight.submission_path} "
                f"context_guard={preflight.context_guard_available}"
            )
            if not preflight.ready:
                trace.trace(
                    "transaction preflight blocked: "
                    f"codes={','.join(getattr(preflight, "reason_codes", ()) or ()) or 'unknown'}"
                )
                reason = "; ".join(preflight.reasons)
                raise TransactionRejected(
                    reason or f"{self.policy.target_label} send preflight blocked the send.",
                    preflight=preflight,
                )

            if preferred_hwnd and preflight.hwnd != preferred_hwnd:
                raise TransactionRejected(
                    f"The preferred {self.policy.target_label} window disappeared or was replaced; "
                    "the send was stopped instead of retargeting another window.",
                    preflight=preflight,
                )

            selected = self.target.select_for_send(preferred_hwnd=preflight.hwnd)
            if selected != preflight.hwnd:
                raise TransactionRejected(
                    f"{self.policy.target_label}'s preflight target could not be bound safely.",
                    preflight=preflight,
                )

            target_scope = TargetScope(preflight.hwnd, preflight.pid)
            bound_scope = self.target.scope()
            if bound_scope != target_scope:
                raise TransactionRejected(
                    "The send transaction target lease did not match preflight; the send was stopped.",
                    preflight=preflight,
                )

            context = preflight.context
            if context is None:
                context = self.policy.capture_context(preflight.hwnd)
            if context is not None:
                context_hwnd = getattr(context, "hwnd", preflight.hwnd)
                if context_hwnd != preflight.hwnd:
                    raise TransactionRejected(
                        f"{self.policy.target_label} target identity could not be safely captured; "
                        "the send was stopped.",
                        preflight=preflight,
                    )
                if not self.policy.context_matches(context):
                    raise TransactionRejected(
                        f"The {self.policy.target_label} target or conversation changed "
                        "while the message was being prepared.",
                        preflight=preflight,
                    )
            elif self.policy.requires_context:
                raise TransactionRejected(
                    f"{self.policy.target_label} target identity could not be safely captured; "
                    "the send was stopped.",
                    preflight=preflight,
                )

            # Context/UIA inspection above can itself span enough time for a
            # Telegram window to be restarted or replaced. Re-check the lease
            # after context validation so a matching snapshot can never
            # authorize a transaction against a changed live target.
            if self.target.scope() != target_scope:
                raise TransactionRejected(
                    f"{self.policy.target_label}'s target changed while the transaction context "
                    "was being validated; the send was stopped instead of retargeting.",
                    preflight=preflight,
                )

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
    "TelegramTransactionPreparationPolicy",
    "TransactionPreparationPolicy",
    "TransactionRejected",
]
