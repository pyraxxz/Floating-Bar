"""Non-content Telegram window context used to detect conversation switches.

The title is read only to derive a one-way SHA-256 fingerprint. The raw title
is never logged, stored on disk, or exposed in diagnostics. The fingerprint is
kept only for the lifetime of a send attempt and is an additional guard on top
of the authoritative Telegram `(HWND, PID)` scope.
"""

from dataclasses import dataclass
from hashlib import sha256

from . import winapi


def title_fingerprint(title: str) -> str:
    """Return a stable in-memory fingerprint without retaining the title."""
    normalized = (title or "").strip().casefold()
    if not normalized:
        return ""
    return sha256(normalized.encode("utf-8", "surrogatepass")).hexdigest()


@dataclass(frozen=True)
class WindowContext:
    hwnd: int
    pid: int
    title_fp: str

    def matches(self) -> bool:
        """Check HWND/PID and, when available, the title fingerprint."""
        if not self.hwnd or not self.pid:
            return False
        if winapi.get_window_pid(self.hwnd) != self.pid:
            return False
        if not winapi.user32.IsWindow(self.hwnd):
            return False
        if self.title_fp:
            return title_fingerprint(winapi.get_window_title(self.hwnd)) == self.title_fp
        return True


def capture(hwnd: int) -> WindowContext:
    """Capture non-content identity for one Telegram top-level window."""
    pid = winapi.get_window_pid(hwnd) if hwnd else 0
    title = winapi.get_window_title(hwnd) if hwnd else ""
    return WindowContext(hwnd=hwnd or 0, pid=pid, title_fp=title_fingerprint(title))
