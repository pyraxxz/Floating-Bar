"""Fail-closed generic background typing adapter with exact control pinning.

The adapter binds one exact top-level HWND/PID scope and can only post text to a
structurally discovered editable child in that same process. Submission is
performed by the selected adapter policy, and unsupported submit modes are
rejected before any text is delivered.
"""

from dataclasses import dataclass

from . import trace
from . import winapi
from .adapter_submit import submit_background_target, validate_submission_mode
from .control_candidates import (
    InputCandidate,
    best_input_candidate,
    enumerate_input_candidates,
)
from .evidence import EvidenceStrategy, SubmissionEvidence, from_result
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


@dataclass(frozen=True)
class PostSendCheck:
    """Bounded, content-free health check performed after injection."""

    scope_alive: bool
    target_alive: bool
    target_hwnd: int
    reason: str = "ok"

    @property
    def healthy(self) -> bool:
        return self.scope_alive and self.target_alive


class BackgroundTypingTarget:
    """Exact-scope adapter for common apps whose current control accepts text."""

    def __init__(self, hwnd: int = 0, pid: int = 0):
        self._scope = TargetScope(hwnd, pid) if hwnd and pid else None
        # A constructor-created target predates an explicit bind operation. Keep
        # the legacy state until bind() can perform an immediate HWND/PID check.
        self._bind_verified = True
        self._pinned_hwnd = 0
        self._pinned_identity = None
        self._adapter_spec = None
        self._last_post_send_check = None
        self._last_submission_evidence = None

    def bind(self, hwnd: int, pid: int, spec=None) -> TargetScope:
        scope = TargetScope(hwnd, pid)
        self._scope = scope
        self._adapter_spec = spec
        self._bind_verified = self._verify_bound_scope(scope)
        self.clear_pinned_input()
        self._last_post_send_check = None
        self._last_submission_evidence = None
        return scope

    @staticmethod
    def _verify_bound_scope(scope: TargetScope) -> bool:
        """Check exact HWND/PID liveness without requiring the window to be visible."""
        if not scope.valid:
            return False
        try:
            if not winapi.user32.IsWindow(scope.hwnd):
                return False
            return winapi.get_window_pid(scope.hwnd) == scope.pid
        except Exception as exc:
            trace.trace(f"background bind liveness check failed safely: {exc}")
            return False

    def bind_adapter(self, spec) -> None:
        self._adapter_spec = spec

    def release(self) -> None:
        self._scope = None
        self._adapter_spec = None
        self._bind_verified = False
        self._last_post_send_check = None
        self._last_submission_evidence = None
        self.clear_pinned_input()

    def scope(self) -> TargetScope:
        if self._scope is None:
            return TargetScope(0, 0)
        return self._scope

    def scope_matches(self, hwnd: int, pid: int) -> bool:
        scope = self._scope
        if not scope or scope.hwnd != hwnd or scope.pid != pid:
            return False
        # A bind can race with a just-created window. Revalidate a previously
        # rejected bind so transient readiness does not become a permanent block.
        if not self._bind_verified:
            self._bind_verified = self._verify_bound_scope(scope)
        return bool(self._bind_verified and self.available())

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
            str(getattr(candidate, "automation_id", "")),
            str(getattr(candidate, "framework_id", "")),
            getattr(candidate, "runtime_id", None),
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

    @property
    def last_post_send_check(self) -> PostSendCheck | None:
        """Return the most recent bounded post-send health result."""
        return self._last_post_send_check

    @property
    def last_submission_evidence(self) -> SubmissionEvidence | None:
        """Return typed evidence produced by the most recent send attempt."""
        return self._last_submission_evidence

    def _record_submission_evidence(self, strategy: str | None, error: str | None = None) -> str | None:
        self._last_submission_evidence = from_result(strategy, error)
        if isinstance(strategy, EvidenceStrategy):
            return strategy
        if self._last_submission_evidence is None or strategy is None:
            return strategy
        return EvidenceStrategy(strategy, self._last_submission_evidence)

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

    def _post_send_check(self, target_hwnd: int) -> PostSendCheck:
        """Check only window/process liveness; never inspect message content."""
        scope = self._scope
        if scope is None or not scope.valid:
            return PostSendCheck(False, False, target_hwnd, "scope-missing")
        try:
            scope_alive = self.available()
        except Exception:
            scope_alive = False
        if not scope_alive:
            return PostSendCheck(False, False, target_hwnd, "scope-changed")
        try:
            target_alive = bool(
                target_hwnd and
                winapi.user32.IsWindow(target_hwnd) and
                winapi.get_window_pid(target_hwnd) == scope.pid
            )
        except Exception:
            target_alive = False
        if not target_alive:
            return PostSendCheck(True, False, target_hwnd, "target-changed")
        return PostSendCheck(True, True, target_hwnd, "ok")

    def type_text(self, text: str) -> int:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("background typing text must be non-empty")
        if self._pinned_hwnd:
            target = self._pinned_target()
        else:
            target = self._focused_target()
        winapi.post_text(target, text, expected_pid=self.scope().pid)
        return target

    def prepare_submission_verification(self):
        """Optional adapter hook executed immediately before text injection."""
        return None

    def begin_submission_verification(self, target_hwnd: int, state):
        """Optional adapter hook executed after injection and before submit."""
        return state

    def finish_submission_verification(self, target_hwnd: int, state, strategy: str) -> str:
        """Optional adapter hook executed after submit; defaults to raw strategy."""
        return strategy

    def _verification_unavailable_after_submit(self, target: int, phase: str) -> str:
        """Record liveness after an ambiguous post-injection outcome."""
        trace.trace(
            f"stage=submit exception phase={phase} "
            "outcome=verification-unavailable"
        )
        self._last_post_send_check = self._post_send_check(target)
        trace.trace(
            "stage=post-send "
            f"scope={'ok' if self._last_post_send_check.scope_alive else 'changed'} "
            f"target={'ok' if self._last_post_send_check.target_alive else 'changed'} "
            f"reason={self._last_post_send_check.reason}"
        )
        return self._record_submission_evidence(
            "posted-enter (verification-unavailable)"
        )

    def send(self, text: str) -> str:
        validate_submission_mode(self._adapter_spec)
        self._last_submission_evidence = None
        spec_key = getattr(self._adapter_spec, "key", "legacy")
        trace.trace(f"stage=adapter key={spec_key}")
        verification_state = None
        try:
            try:
                verification_state = self.prepare_submission_verification()
            except Exception:
                verification_state = None
                trace.trace("stage=verification baseline unavailable")

            target = self.type_text(text)
            trace.trace(f"stage=target hwnd={target} scope={self.scope().hwnd}/{self.scope().pid}")
            try:
                verification_state = self.begin_submission_verification(target, verification_state)
            except Exception:
                verification_state = None
                trace.trace("stage=verification post-injection unavailable")

            try:
                strategy = submit_background_target(self._adapter_spec, target, expected_pid=self.scope().pid)
            except Exception:
                return self._verification_unavailable_after_submit(target, "submission")

            self._last_post_send_check = self._post_send_check(target)
            trace.trace(
                "stage=post-send "
                f"scope={'ok' if self._last_post_send_check.scope_alive else 'changed'} "
                f"target={'ok' if self._last_post_send_check.target_alive else 'changed'} "
                f"reason={self._last_post_send_check.reason}"
            )
            if not self._last_post_send_check.healthy:
                return self._record_submission_evidence(
                    "posted-enter (verification-unavailable)"
                )

            try:
                final_strategy = self.finish_submission_verification(
                    target,
                    verification_state,
                    strategy,
                )
            except Exception:
                return self._record_submission_evidence(
                    "posted-enter (verification-unavailable)"
                )
            return self._record_submission_evidence(final_strategy)
        finally:
            self.clear_pinned_input()


__all__ = ["BackgroundTypingTarget", "PostSendCheck", "TargetProbe"]
