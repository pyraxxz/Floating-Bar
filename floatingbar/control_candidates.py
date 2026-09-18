"""Content-free discovery and scoring of candidate text-input controls.

This module inspects UI Automation structure only: control type, class name,
geometry, editability, enabled/visible state, and focus. It never reads the
control's text/value.
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
    automation_id: str = ""
    framework_id: str = ""
    runtime_id: tuple[int, ...] | None = None

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def is_likely_composer_shape(self) -> bool:
        """Use geometry only as a weak signal; never infer from message content."""
        return self.width >= 180 and self.height >= 24


_EDIT_TYPES = {"Edit", "Document"}


def _candidate_from_element(element, pid: int, top_hwnd: int) -> InputCandidate | None:
    try:
        rect = element.rectangle()
        hwnd = int(element.handle)
        info = element.element_info
        control_type = str(info.control_type or "")
        class_name = str(info.class_name or "")
        automation_id = str(getattr(info, "automation_id", "") or "")
        framework_id = str(getattr(info, "framework_id", "") or "")
        raw_runtime_id = getattr(info, "runtime_id", None)
        try:
            runtime_id = tuple(int(part) for part in raw_runtime_id) or None
        except (TypeError, ValueError):
            runtime_id = None
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
            automation_id=automation_id,
            framework_id=framework_id,
            runtime_id=runtime_id,
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
        candidates = []
        for control_type in ("Edit", "Document"):
            for element in root.descendants(control_type=control_type):
                candidate = _candidate_from_element(element, pid, top_hwnd)
                if candidate is not None:
                    candidates.append(candidate)
    except Exception:
        return ()

    unique = {candidate.hwnd: candidate for candidate in candidates}
    return tuple(unique.values())


def candidate_score(candidate: InputCandidate, *, max_bottom: int | None = None) -> tuple:
    """Return a deterministic, content-free structural score.

    Focus remains the strongest signal. Composer-like geometry and lower-page
    placement are supporting signals, while all ties are resolved by geometry
    and HWND so the choice stays deterministic.
    """
    bottom_distance = 0
    if max_bottom is not None:
        bottom_distance = max(0, max_bottom - candidate.center_y)
    return (
        int(candidate.focused),
        int(candidate.is_likely_composer_shape),
        candidate.area,
        -bottom_distance,
        -candidate.top,
        -candidate.left,
        -candidate.hwnd,
    )


def best_input_candidate(
    candidates: Iterable[InputCandidate], *, max_bottom: int | None = None
) -> InputCandidate | None:
    """Return the strongest structural candidate without content reads."""
    candidates = tuple(candidates)
    if not candidates:
        return None
    return max(candidates, key=lambda item: candidate_score(item, max_bottom=max_bottom))


__all__ = ["InputCandidate", "enumerate_input_candidates", "best_input_candidate", "candidate_score"]
