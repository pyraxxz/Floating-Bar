"""Terminal-specific background typing target.

Windows Terminal is treated more strictly than the generic adapter: the
focused child must also appear in the content-free editable-control inventory
for the bound window. This prevents sending to an unrelated focused child
when the terminal exposes several UI controls.
"""

from .generic_target import BackgroundTypingTarget


class TerminalTypingTarget(BackgroundTypingTarget):
    """Fail-closed target for Windows Terminal/console-host style windows."""

    def _focused_target(self) -> int:
        focused = super()._focused_target()
        candidates = self.input_candidates()
        if not any(candidate.hwnd == focused for candidate in candidates):
            raise RuntimeError(
                "terminal focused control is not a discovered editable target"
            )
        return focused


__all__ = ["TerminalTypingTarget"]
