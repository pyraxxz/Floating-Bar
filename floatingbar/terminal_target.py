"""Terminal-specific background typing target.

Windows Terminal is treated more strictly than the generic adapter: the target
must be a content-free structurally discovered editable control. When several
editable controls exist, a discovered candidate is preferred over an unrelated
focused field.
"""

from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate
from . import winapi


class TerminalTypingTarget(BackgroundTypingTarget):
    """Fail-closed target for Windows Terminal/console-host style windows."""

    def _terminal_candidates(self):
        return tuple(self.input_candidates())

    def _is_terminal_control(self, hwnd: int) -> bool:
        return any(candidate.hwnd == hwnd for candidate in self._terminal_candidates())

    def _focused_target(self) -> int:
        """Choose a discovered terminal control without requiring foreground focus."""
        candidates = self._terminal_candidates()
        if not candidates:
            raise RuntimeError("terminal target has no discovered editable target")

        scope = self._scope
        try:
            focused_hwnd = winapi.get_focused_hwnd(scope.hwnd) if scope else 0
        except Exception:
            focused_hwnd = 0

        focused = next(
            (candidate for candidate in candidates if candidate.hwnd == focused_hwnd),
            None,
        )
        if focused is not None:
            return focused.hwnd

        preferred = best_input_candidate(candidates)
        if preferred is None:
            raise RuntimeError("terminal target has no usable discovered target")
        return preferred.hwnd

    def pin_best_input(self):
        candidates = self._terminal_candidates()
        candidate = best_input_candidate(candidates)
        if candidate is None:
            raise RuntimeError("background typing target has no discovered terminal control")
        scope = self.scope()
        if not scope.hwnd or candidate.pid != scope.pid:
            raise RuntimeError("background typing candidate escaped the bound process")
        self._pinned_hwnd = candidate.hwnd
        return candidate

    def _pinned_target(self) -> int:
        pinned = super()._pinned_target()
        if not self._is_terminal_control(pinned):
            raise RuntimeError(
                "terminal pinned control is not a discovered editable target"
            )
        return pinned


__all__ = ["TerminalTypingTarget"]
