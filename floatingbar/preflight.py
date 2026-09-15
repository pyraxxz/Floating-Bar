"""Read-only safety preflight for the Telegram send path.

The preflight deliberately performs discovery and validation only. It never
posts mouse/keyboard messages, changes foreground focus, reads message text,
or touches the clipboard. Its purpose is to explain whether the current
Telegram window is a viable target before a live send is attempted.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from . import winapi
from .context import WindowContext, capture
from .target import TelegramNotFound, TelegramTarget


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    reasons: Tuple[str, ...]
    hwnd: int = 0
    pid: int = 0
    focused_hwnd: int = 0
    focused_pid: int = 0
    minimized: bool = False
    compose_click: Optional[Tuple[int, int]] = None
    send_name: str = ""
    send_point: Optional[Tuple[int, int]] = None
    send_evidence_score: float = 0.0
    submission_path: str = "unavailable"
    scope_stable: bool = False
    context: Optional[WindowContext] = None
    context_guard_available: bool = False
    context_stable: bool = False

    @property
    def button_available(self) -> bool:
        return bool(self.send_name or self.send_point)

    @property
    def status(self) -> str:
        """Human-readable safety state for diagnostics."""
        if not self.ready:
            return "blocked"
        if not self.context_guard_available:
            return "ready-with-degraded-context"
        return "ready"


def _context_transition_stable(
    initial: Optional[WindowContext],
    final: WindowContext,
) -> bool:
    """Return whether every initially-available non-content anchor survived.

    A later-discovered anchor is allowed; an anchor that was already available
    but then disappears or changes is treated as context drift.
    """
    if initial is None:
        return True
    if initial.process_name and final.process_name != initial.process_name:
        return False
    if initial.title_fp and final.title_fp != initial.title_fp:
        return False
    if initial.chat_runtime_id and final.chat_runtime_id != initial.chat_runtime_id:
        return False
    if initial.chat_name_fp and final.chat_name_fp != initial.chat_name_fp:
        return False
    return True


def _blocked(reason: str) -> PreflightResult:
    """Return a deterministic blocked result for an unsafe inspection failure."""
    return PreflightResult(ready=False, reasons=(reason,))


def run(target: TelegramTarget, preferred_hwnd: int = 0) -> PreflightResult:
    """Perform a non-invasive readiness check for a Telegram send."""
    reasons = []

    try:
        hwnd = target.select_for_send(preferred_hwnd=preferred_hwnd)
    except TelegramNotFound:
        return _blocked("Telegram Desktop was not found.")
    except Exception:
        return _blocked("Telegram target could not be inspected safely.")

    if not hwnd:
        return _blocked("Telegram Desktop was not found.")

    try:
        pid = target.scope()[1]
    except Exception:
        return _blocked("Telegram target scope could not be inspected safely.")

    try:
        minimized = winapi.is_minimized(hwnd)
    except Exception:
        return _blocked("Telegram minimized state could not be inspected safely.")
    if minimized:
        reasons.append("Telegram is minimized; background client clicks are unsafe.")

    focused_hwnd = 0
    focused_pid = 0
    try:
        focused_hwnd = winapi.get_focused_hwnd(hwnd)
        focused_pid = winapi.get_window_pid(focused_hwnd) if focused_hwnd else 0
    except Exception:
        reasons.append("Telegram focus state could not be inspected safely.")
    if focused_hwnd and focused_pid and focused_pid != pid:
        reasons.append("Telegram does not currently own the focused child HWND.")

    initial_context = None
    try:
        initial_context = capture(hwnd)
    except Exception:
        pass

    compose_click = None
    compose_runtime_id = ()
    send_name = ""
    send_point = None
    send_evidence_score = 0.0
    submission_path = "unavailable"

    try:
        box = target.compose_box()
        try:
            compose_runtime_id = tuple(box.element_info.runtime_id)
        except Exception:
            compose_runtime_id = ()
        compose_click = target.compose_click_point(box)
        if compose_click is None:
            reasons.append("The compose control has no usable click geometry.")
        else:
            info = target.send_button_click(near_box=box)
            if info is not None:
                send_name = info.name or ""
                send_point = (info.client_x, info.client_y)
                send_evidence_score = float(info.evidence_score)
                submission_path = "send-button"
            else:
                submission_path = "enter-fallback"
                reasons.append(
                    "No safe Send button candidate was exposed; Enter fallback is required."
                )
    except TelegramNotFound as exc:
        reasons.append(str(exc))
    except Exception:
        reasons.append("Telegram compose controls could not be inspected safely.")

    try:
        current_hwnd, current_pid = target.scope()
    except Exception:
        current_hwnd, current_pid = 0, 0
        reasons.append("Telegram target scope could not be revalidated safely.")
    scope_stable = (
        current_hwnd == hwnd and
        current_pid == pid and
        bool(current_hwnd and current_pid)
    )
    if not scope_stable and not any("scope" in reason for reason in reasons):
        reasons.append("Telegram target scope changed during preflight.")

    context = None
    context_guard_available = False
    context_stable = False
    context_inspection_ok = True
    try:
        context = capture(hwnd, compose_runtime_id=compose_runtime_id)
        context_guard_available = context.guard_available

        if not _context_transition_stable(initial_context, context):
            reasons.append("Telegram conversation context changed during preflight.")
            context_stable = False
        elif context_guard_available:
            context_stable = context.matches()

        if context_guard_available and not context_stable:
            if not any("context changed" in reason for reason in reasons):
                if not context.matches():
                    reasons.append("Telegram conversation context changed during preflight.")
        elif not context_guard_available:
            context_stable = False
            reasons.append(
                "Telegram conversation context could not be verified safely."
            )
    except Exception:
        context_inspection_ok = False
        reasons.append("Telegram conversation context could not be inspected safely.")

    context_ok = (
        context_inspection_ok and
        (not context_guard_available or context_stable)
    )

    ready = bool(
        hwnd and
        pid and
        not minimized and
        compose_click is not None and
        scope_stable and
        context_ok
    )
    return PreflightResult(
        ready=ready,
        reasons=tuple(reasons),
        hwnd=hwnd,
        pid=pid,
        focused_hwnd=focused_hwnd,
        focused_pid=focused_pid,
        minimized=minimized,
        compose_click=compose_click,
        send_name=send_name,
        send_point=send_point,
        send_evidence_score=send_evidence_score,
        submission_path=submission_path,
        scope_stable=scope_stable,
        context=context,
        context_guard_available=context_guard_available,
        context_stable=context_stable,
    )
