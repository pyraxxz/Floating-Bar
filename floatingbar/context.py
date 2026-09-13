"""Non-content Telegram window context used to detect conversation switches.

The title is read only to derive a one-way, per-process HMAC fingerprint. A
session-scoped compose-control runtime ID is also captured when available;
it is used only as an in-memory structural anchor and is never logged or
persisted. The Telegram process basename is also retained as a non-content
identity anchor. Raw title text, message content, and the HMAC key are never
logged, stored on disk, or exposed in diagnostics.
"""

from dataclasses import dataclass
from hashlib import sha256
import hmac
import secrets
from typing import Optional, Tuple

from . import winapi


_SESSION_KEY = secrets.token_bytes(32)
_GENERIC_TITLES = {
    "telegram",
    "telegram desktop",
}


def title_fingerprint(title: str) -> str:
    """Return a stable per-process HMAC without retaining generic titles."""
    normalized = (title or "").strip().casefold()
    if not normalized or normalized in _GENERIC_TITLES:
        return ""
    return hmac.new(
        _SESSION_KEY,
        normalized.encode("utf-8", "surrogatepass"),
        sha256,
    ).hexdigest()


def _process_basename(pid: int) -> str:
    """Return a non-content process basename, or empty when unavailable."""
    if not pid:
        return ""
    try:
        image = winapi.get_process_image_name(pid)
        if not isinstance(image, str) or not image:
            return ""
        return image.rsplit("\\", 1)[-1].casefold()
    except Exception:
        return ""


def compose_runtime_id_present(hwnd: int, runtime_id: Tuple[int, ...]) -> bool:
    """Return whether a content-free UIA Edit anchor still exists on the window."""
    if not hwnd or not runtime_id:
        return False
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=hwnd)
        window = app.window(handle=hwnd).wrapper_object()
        for edit in window.descendants(control_type="Edit"):
            try:
                if tuple(edit.element_info.runtime_id) == tuple(runtime_id):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


@dataclass(frozen=True)
class WindowContext:
    hwnd: int
    pid: int
    title_fp: str
    compose_runtime_id: Tuple[int, ...] = ()
    process_name: str = ""

    @property
    def guard_available(self) -> bool:
        """Whether at least one non-content conversation-level anchor is available."""
        return bool(self.title_fp or self.compose_runtime_id)

    def matches(self) -> bool:
        """Check HWND/PID plus every context anchor captured for this attempt."""
        if not self.hwnd or not self.pid:
            return False
        if winapi.get_window_pid(self.hwnd) != self.pid:
            return False
        if not winapi.user32.IsWindow(self.hwnd):
            return False
        if self.process_name and _process_basename(self.pid) != self.process_name:
            return False
        if self.title_fp:
            if title_fingerprint(winapi.get_window_title(self.hwnd)) != self.title_fp:
                return False
        if self.compose_runtime_id:
            if not compose_runtime_id_present(self.hwnd, self.compose_runtime_id):
                return False
        return True


def capture(
    hwnd: int,
    compose_runtime_id: Optional[Tuple[int, ...]] = None,
) -> WindowContext:
    """Capture non-content identity for one Telegram top-level window."""
    pid = winapi.get_window_pid(hwnd) if hwnd else 0
    title = winapi.get_window_title(hwnd) if hwnd else ""
    rid = tuple(compose_runtime_id or ())
    return WindowContext(
        hwnd=hwnd or 0,
        pid=pid,
        title_fp=title_fingerprint(title),
        compose_runtime_id=rid,
        process_name=_process_basename(pid),
    )
