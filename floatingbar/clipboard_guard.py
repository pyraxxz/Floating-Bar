"""Full-fidelity clipboard save/restore via raw Win32 — no pyperclip.

The guard snapshots every HGLOBAL-backed clipboard format so the opt-in
foreground fallback does not destroy screenshots, copied files, HTML/RTF, or
application-specific data. A failed snapshot is distinguished from a truly
empty clipboard so recovery never accidentally clears the user's clipboard.
"""

import ctypes
import time
from typing import Optional, List, Tuple

import ctypes.wintypes as wintypes

from . import winapi

user32 = winapi.user32
kernel32 = winapi.kernel32

CF_TEXT = 1
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_OEMTEXT = 7
CF_DIB = 8
CF_PALETTE = 9
CF_PENDATA = 10
CF_WAVE = 12
CF_UNICODETEXT = 13
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_LOCALE = 16
CF_DIBV5 = 17
CF_DSPBITMAP = 130
CF_DSPMETAFILEPICT = 131
CF_DSPENHMETAFILE = 142

_UNCOPYABLE = {
    CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE,
    CF_DSPBITMAP, CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE,
}

GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
user32.EnumClipboardFormats.restype = wintypes.UINT
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


def _open_with_retries(retries: int, delay: float) -> bool:
    for attempt in range(retries):
        if user32.OpenClipboard(None):
            return True
        if attempt == retries - 1:
            return False
        time.sleep(delay)
    return False


def snapshot(
    retries: int = 3, delay: float = 0.05
) -> Optional[List[Tuple[int, bytes]]]:
    """Capture all copyable HGLOBAL-backed formats.

    Returns ``None`` when the clipboard cannot be opened, and ``[]`` when the
    clipboard was successfully opened but contained no supported formats.
    """
    if not _open_with_retries(retries, delay):
        return None
    try:
        captured = []
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in _UNCOPYABLE:
                handle = user32.GetClipboardData(fmt)
                if handle:
                    size = kernel32.GlobalSize(handle)
                    if size:
                        ptr = kernel32.GlobalLock(handle)
                        if ptr:
                            try:
                                captured.append(
                                    (fmt, ctypes.string_at(ptr, size))
                                )
                            finally:
                                kernel32.GlobalUnlock(handle)
            fmt = user32.EnumClipboardFormats(fmt)
        return captured
    finally:
        user32.CloseClipboard()


def restore(
    captured: Optional[List[Tuple[int, bytes]]],
    retries: int = 3,
    delay: float = 0.05,
) -> bool:
    """Restore a successful snapshot; ``None`` means snapshot failed."""
    if captured is None:
        return False
    if not _open_with_retries(retries, delay):
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        for fmt, data in captured:
            handle = kernel32.GlobalAlloc(GHND, len(data))
            if not handle:
                continue
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                continue
            try:
                ctypes.memmove(ptr, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
        return True
    finally:
        user32.CloseClipboard()


def set_text(text: str, retries: int = 3, delay: float = 0.05) -> bool:
    """Put plain Unicode text on the clipboard for the paste fallback."""
    payload = text.encode("utf-16-le") + b"\x00\x00"
    if not _open_with_retries(retries, delay):
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        handle = kernel32.GlobalAlloc(GHND, len(payload))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        try:
            ctypes.memmove(ptr, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


class preserved_clipboard:
    """Context manager that restores the user's clipboard when possible."""

    def __init__(self, retries: int = 3, delay: float = 0.05):
        self._retries = retries
        self._delay = delay
        self._captured = None

    def __enter__(self):
        self._captured = snapshot(self._retries, self._delay)
        if self._captured is None:
            # Snapshot failure is deliberately not converted to an empty
            # snapshot. The caller may continue best-effort, but __exit__ will
            # never clear the user's clipboard as a side effect of recovery.
            return self
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._captured is not None:
                restore(self._captured, self._retries, self._delay)
        except Exception:
            pass
        return False
