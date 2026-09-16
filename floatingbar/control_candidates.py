"""Content-free discovery of candidate text-input controls.

This module is deliberately separate from send execution. It inspects UI
Automation structure only: control type, class name, geometry, editability,
enabled/visible state, and focus. It never reads the control's text/value.
"""

from dataclasses import dataclass
from typing import Iterable

from . import winapi


@dataclass(frozen=True)
class InputCandidate:
    hwnd: int
    pid: int
    class_name: str
    control_type: str
    left: int
    top: int
    right: int
    bottom: int
    focused: bool
    enabled: bool
    visible: bool

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height


_EDIT_TYPES = {"Edit", "Document"}


def _candidate_from_element(element, pid: int, top_hwnd: int) -> InputCandidate | None:
    try:
        rect = element.rectangle()
        hwnd = int(element.handle)
        control_type = str(element.element_info.control_type or "")
        class_name = str(element.element_info.class_name or "")
        visible = bool(element.is_visible())
        enabled = bool(element.is_enabled())
        if not hwnd or not visible or not enabled:
            return None
        if control_type not in _EDIT_TYPES:
            return None
        if winapi.get_window_pid(hwnd) != pid:
            return None
        return InputCandidate(
            hwnd=hwnd,
            pid=pid,
            class_name=class_name,
            control_type=control_type,
            left=int(rect.left),
            top=int(rect.top),
            right=int(rect.right),
            bottom=int(rect.bottom),
            focused=(winapi.get_focused_hwnd(top_hwnd) == hwnd),
            enabled=enabled,
            visible=visible,
        )
    except Exception:
        return None


def enumerate_input_candidates(top_hwnd: int) -> tuple[InputCandidate, ...]:
    """Enumerate visible editable controls without reading their text."""
    if not top_hwnd or not winapi.user32.IsWindow(top_hwnd):
        return ()
    pid = winapi.get_window_pid(top_hwnd)
    if not pid:
        return ()

    try:
        from pywinauto import Desktop

        root = Desktop(backend="uia").window(handle=top_hwnd)
        elements = root.descendants(control_type="Edit")
        candidates = []
        for element in elements:
            candidate = _candidate_from_element(element, pid, top_hwnd)
            if candidate is not None:
                candidates.append(candidate)

        # Some apps expose a multiline document rather than Edit. Add those
        # controls separately without ever reading their content.
        for element in root.descendants(control_type="Document"):
            candidate = _candidate_from_element(element, pid, top_hwnd)
            if candidate is not None:
                candidates.append(candidate)
    except Exception:
        return ()

    unique = {candidate.hwnd: candidate for candidate in candidates}
    return tuple(sorted(
        unique.values(),
        key=lambda item: (
            not item.focused,
            -item.area,
            item.top,
            item.left,
            item.hwnd,
        ),
    ))


def best_input_candidate(candidates: Iterable[InputCandidate]) -> InputCandidate | None:
    """Return the highest-confidence structural candidate, without content reads."""
    candidates = tuple(candidates)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            not item.focused,
            -item.area,
            item.top,
            item.left,
            item.hwnd,
        ),
    )[0]


__all__ = ["InputCandidate", "enumerate_input_candidates", "best_input_candidate"]
