"""Terminal-specific background typing target.

Windows Terminal is treated more strictly than the generic adapter: the target
must be a content-free structurally discovered editable control. This applies
to both the current focus and any pinned send target.
"""

from .generic_target import BackgroundTypingTarget


class TerminalTypingTarget(BackgroundTypingTarget):
    """Fail-closed target for Windows Terminal/console-host style windows."""

    def _is_terminal_control(self, hwnd: int) -> bool:
        return any(candidate.hwnd == hwnd for candidate in self.input_candidates())

    def _focused_target(self) -> int:
        focused = super()._focused_target()
        if not self._is_terminal_control(focused):
            raise RuntimeError(
                "terminal focused control is not a discovered editable target"
            )
        return focused

    def _pinned_target(self) -> int:
        pinned = super()._pinned_target()
        if not self._is_terminal_control(pinned):
            raise RuntimeError(
                "terminal pinned control is not a discovered editable target"
            )
        return pinned


__all__ = ["TerminalTypingTarget"]
