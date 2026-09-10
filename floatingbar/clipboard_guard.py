"""Full-fidelity clipboard save/restore via raw Win32 — no pyperclip.

Why not pyperclip: it can only round-trip plain text. If the user's
clipboard held a screenshot (CF_DIB), copied files (CF_HDROP), or HTML/
RTF (registered formats), a text-only save/restore would silently destroy
them. The spec's own requirement R9 says the user's clipboard must be
unmodified "from their perspective" — so we snapshot every HGLOBAL-backed
format present and restore them byte-for-byte.

Formats that are raw GDI handles (CF_BITMAP, CF_PALETTE, CF_METAFILEPICT,
CF_ENHMETAFILE, and the CF_DSP* variants) cannot be byte-copied safely and
are skipped. Everything users actually copy — text, DIB images, file
lists, HTML, RTF, custom app formats — is HGLOBAL-backed and survives.
"""

import ctypes
import time

import ctypes.wintypes as wintypes

from . import winapi

user32 = winapi.user32
kernel32 = winapi.kernel32

# --- Clipboard format ids ---------------------------------------------------
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

# Handle-based formats we cannot faithfully byte-copy.
_UNCOPYABLE = {CF_BITMAP, CF_METAFILEPICT, CF_PALETTE, CF_ENHMETAFILE,
               CF_DSPBITMAP, CF_DSPMETAFILEPICT, CF_DSPENHMETAFILE}

GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
GHND = GMEM_MOVEABLE | GMEM_ZEROINIT

# --- Signatures -------------------------------------------------------------
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


def snapshot(retries: int = 3, delay: float = 0.05) -> list:
    """Capture every HGLOBAL-backed format on the clipboard as
    [(format_id, bytes), ...]. Returns [] if the clipboard can't be
    opened (treat as 'nothing to preserve' rather than failing the send)."""
    if not _open_with_retries(retries, delay):
        return []
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
                                captured.append((fmt, ctypes.string_at(ptr, size)))
                            finally:
                                kernel32.GlobalUnlock(handle)
            fmt = user32.EnumClipboardFormats(fmt)
        return captured
    finally:
        user32.CloseClipboard()


def restore(captured: list, retries: int = 3, delay: float = 0.05) -> bool:
    """Put a snapshot back, replacing whatever is on the clipboard now.
    Best effort: on failure the clipboard keeps the relay text (rare,
    harmless, and logged nowhere)."""
    if not _open_with_retries(retries, delay):
        return False
    try:
        user32.EmptyClipboard()
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
            user32.SetClipboardData(fmt, handle)  # system owns it from here
        return True
    finally:
        user32.CloseClipboard()


def set_text(text: str, retries: int = 3, delay: float = 0.05) -> bool:
    """Put plain text on the clipboard as CF_UNICODETEXT (+ CF_TEXT for
    legacy consumers)."""
    payload = text.encode("utf-16-le") + b"\x00\x00"
    if not _open_with_retries(retries, delay):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GHND, len(payload))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False
        return True
    finally:
        user32.CloseClipboard()


class preserved_clipboard:
    """Context manager: snapshot on entry, restore on exit.

    with preserved_clipboard() as clip:
        clipboard_guard.set_text(relay_text)
        ... paste ...
    # user's clipboard content is back, whatever format it was
    """

    def __init__(self, retries: int = 3, delay: float = 0.05):
        self._retries = retries
        self._delay = delay
        self._captured = []

    def __enter__(self):
        self._captured = snapshot(self._retries, self._delay)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            restore(self._captured, self._retries, self._delay)
        except Exception:
            pass  # clipboard restore is best-effort by design
        return False
