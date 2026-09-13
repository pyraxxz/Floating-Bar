"""Small structural contract for background-app targets.

The contract is intentionally capability-sized: it names the operations the
send transaction already performs today, while Telegram remains the only
production implementation. Future adapters can satisfy this protocol without
forcing the overlay or injector to know their application-specific UIA model.
"""

from typing import Any, List, Optional, Protocol, Tuple, runtime_checkable

from .transaction import TargetScope


@runtime_checkable
class BackgroundTarget(Protocol):
    """Operations required by the current background send transaction."""

    def select_for_send(self, preferred_hwnd: int = 0) -> int:
        """Return the top-level window selected for this send attempt."""

    def scope(self) -> TargetScope:
        """Return the currently selected immutable HWND/PID scope."""

    def is_available(self) -> bool:
        """Return whether a usable target is currently discoverable."""

    def compose_box(self) -> Any:
        """Locate the application's editable compose/control surface."""

    def compose_click_point(self, compose_box: Any) -> Optional[Tuple[int, int]]:
        """Return client-relative coordinates for a safe compose click."""

    def edit_audit(self) -> Tuple[Optional[Any], List[Tuple[Any, str]]]:
        """Return a content-free edit audit (value lengths only)."""

    def remember_compose(self, edit: Any) -> None:
        """Remember a validated compose control for this target session."""

    def send_button_click(self, near_box: Any = None) -> Optional[Tuple[str, int, int]]:
        """Return a safe Send candidate or ``None`` when no safe candidate exists."""


__all__ = ["BackgroundTarget"]
