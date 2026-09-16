"""Terminal-specific background typing target.

Windows Terminal is treated more strictly than the generic adapter: the target
must be a content-free structurally discovered editable control. When several
editable controls exist, a discovered candidate is preferred over an unrelated
focused field.
"""

from .generic_target import BackgroundTypingTarget
from .control_candidates import best_input_candidate


class TerminalTypingTarget(BackgroundTypingTarget):
    """Fail-closed target for Windows Terminal/console-host style windows."""

    def _terminal_candidates(self):
        return tuple(self.input_candidates())

    def _is_terminal_control(self, hwnd: int) -> bool:
        return any(candidate.hwnd == hwnd for candidate in self._terminal_candidates())

    def _focused_target(self) -> int:
        focused = super()._focused_target()
        candidates = self._terminal_candidates()
        if any(candidate.hwnd == focused for candidate in candidates):
            return focused
        preferred = best_input_candidate(candidates)
        if preferred is None:
            raise RuntimeError(
                "terminal focused control is not a discovered editable target"
            )
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
