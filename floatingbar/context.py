"""Non-content Telegram window context used to detect conversation switches.

The title is read only to derive a one-way, per-process HMAC fingerprint. A
session-scoped compose-control runtime ID and, when uniquely exposed by UIA,
a selected chat-row anchor are also captured as in-memory structural hints.
The Telegram process basename is retained as a non-content identity anchor.
Raw title text, chat-row names, message content, and the HMAC key are never
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


def _selected_chat_anchor(hwnd: int) -> Tuple[Tuple[int, ...], str]:
    """Return a unique selected left-pane chat anchor when UIA exposes one."""
    if not hwnd:
        return (), ""
    try:
        from pywinauto import Application

        app = Application(backend="uia").connect(handle=hwnd)
        window = app.window(handle=hwnd).wrapper_object()
        window_rect = window.rectangle()
        cutoff = window_rect.left + int(max(1, window_rect.width()) * 0.60)
        anchors = []
        for item in window.descendants(control_type="ListItem"):
            try:
                rect = item.rectangle()
            except Exception:
                continue
            if rect.width() <= 80 or rect.left >= cutoff:
                continue
            try:
                if not item.is_selected():
                    continue
            except Exception:
                continue
            try:
                runtime_id = tuple(item.element_info.runtime_id)
            except Exception:
                runtime_id = ()
            try:
                name = item.element_info.name or ""
            except Exception:
                name = ""
            name_fp = title_fingerprint(name)
            if runtime_id or name_fp:
                anchors.append((runtime_id, name_fp))

        if len(anchors) == 1:
            return anchors[0]
    except Exception:
        pass
    return (), ""


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
    chat_runtime_id: Tuple[int, ...] = ()
    chat_name_fp: str = ""

    @property
    def guard_available(self) -> bool:
        """Whether at least one non-content conversation-level anchor is available."""
        return bool(
            self.title_fp
            or self.compose_runtime_id
            or self.chat_runtime_id
            or self.chat_name_fp
        )

    def matches(self) -> bool:
        """Check HWND/PID plus every context anchor captured for this attempt.

        Context validation is a safety gate. Any unexpected Windows/UIA failure
        therefore fails closed instead of escaping as an unchecked exception.
        """
        try:
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
            if self.chat_runtime_id or self.chat_name_fp:
                current_runtime_id, current_name_fp = _selected_chat_anchor(self.hwnd)
                if not current_runtime_id and not current_name_fp:
                    return False
                if self.chat_runtime_id and current_runtime_id != self.chat_runtime_id:
                    return False
                if self.chat_name_fp and current_name_fp != self.chat_name_fp:
                    return False
            return True
        except Exception:
            return False


def capture(
    hwnd: int,
    compose_runtime_id: Optional[Tuple[int, ...]] = None,
) -> WindowContext:
    """Capture non-content identity for one Telegram top-level window."""
    pid = winapi.get_window_pid(hwnd) if hwnd else 0
    title = winapi.get_window_title(hwnd) if hwnd else ""
    rid = tuple(compose_runtime_id or ())
    chat_runtime_id, chat_name_fp = _selected_chat_anchor(hwnd)
    return WindowContext(
        hwnd=hwnd or 0,
        pid=pid,
        title_fp=title_fingerprint(title),
        compose_runtime_id=rid,
        process_name=_process_basename(pid),
        chat_runtime_id=chat_runtime_id,
        chat_name_fp=chat_name_fp,
    )
