"""Content-free catalog of user-facing top-level Windows.

This module is groundwork for the orb's background-app picker. It deliberately
keeps only structural identity needed for selection: HWND/PID, process
basename, window area, and whether the window is foreground. Window titles are
used only by Win32 to determine whether a window is user-facing; raw titles
are never returned or persisted.
"""

from dataclasses import dataclass
from typing import Iterable, Tuple

from . import winapi


@dataclass(frozen=True)
class BackgroundWindow:
    """A selectable top-level application window without raw title content."""

    hwnd: int
    pid: int
    process_name: str
    area: int
    foreground: bool = False
    window_class: str = ""

    @property
    def label(self) -> str:
        """Human-facing application label derived only from the process image."""
        return self.process_name or "Unknown application"


def enumerate_background_windows(
    *,
    exclude_hwnds: Iterable[int] = (),
    include_minimized: bool = False,
) -> Tuple[BackgroundWindow, ...]:
    """Return user-facing top-level windows, largest/foreground first.

    Minimized windows remain opt-in so callers that need a strict visible-only
    catalog keep the old behavior. The production background picker explicitly
    enables them because a minimized app is still an open background target;
    later target probing decides whether it exposes a usable input control.
    """
    excluded = {int(hwnd) for hwnd in exclude_hwnds if hwnd}
    foreground = winapi.get_foreground_window()
    results = []

    for hwnd in winapi._enum_windows():
        if not hwnd or hwnd in excluded:
            continue
        try:
            if not winapi._is_candidate_window(hwnd):
                continue
            if not include_minimized and winapi.is_minimized(hwnd):
                continue
            pid = winapi.get_window_pid(hwnd)
            image = winapi.get_process_image_name(pid)
            process_name = image.rsplit("\\", 1)[-1].casefold() if image else ""
            if not process_name:
                continue
            results.append(
                BackgroundWindow(
                    hwnd=hwnd,
                    pid=pid,
                    process_name=process_name,
                    area=winapi.get_window_rect_area(hwnd),
                    foreground=(hwnd == foreground),
                    window_class=str(winapi.get_window_class_name(hwnd) or "").strip(),
                )
            )
        except Exception:
            continue

    results.sort(
        key=lambda item: (
            not item.foreground,
            -item.area,
            item.process_name,
            item.hwnd,
        )
    )
    return tuple(results)


__all__ = ["BackgroundWindow", "enumerate_background_windows"]
