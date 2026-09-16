"""Global hotkey registration for summoning the orb without a click.

The hotkey is registered on a dedicated thread and its WM_HOTKEY messages are
marshalled back to the Tk main thread with ``root.after``. The dispatcher never
touches Tk widgets from its worker thread and fails closed if the chosen
shortcut is already owned by another application.
"""

from __future__ import annotations

import ctypes
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional

if sys.platform != "win32":
    raise ImportError("floatingbar is Windows-only")

import ctypes.wintypes as wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_HOTKEY_ID = 1

user32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


@dataclass(frozen=True)
class HotkeySpec:
    """A single global hotkey made from modifier flags and a virtual-key code."""

    modifiers: int
    virtual_key: int


class GlobalHotkey:
    """Own one global hotkey and marshal its trigger onto the Tk thread."""

    def __init__(self, spec: HotkeySpec, on_trigger: Callable[[], None], tk_root) -> None:
        if not isinstance(spec, HotkeySpec):
            raise TypeError("spec must be HotkeySpec")
        if not 0 <= int(spec.virtual_key) <= 0xFF:
            raise ValueError("virtual_key must be a Win32 virtual-key code")
        if not isinstance(on_trigger, Callable):
            raise TypeError("on_trigger must be callable")
        self._spec = spec
        self._on_trigger = on_trigger
        self._tk_root = tk_root
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._registered = threading.Event()
        self._register_ok = False

    @property
    def is_registered(self) -> bool:
        """Whether RegisterHotKey succeeded for this dispatcher."""
        return self._register_ok

    def start(self) -> None:
        if self._thread is not None:
            return
        self._register_ok = False
        self._registered.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="FloatingBar-Hotkey",
            daemon=True,
        )
        self._thread.start()
        self._registered.wait(timeout=2.0)

    def stop(self) -> None:
        thread = self._thread
        thread_id = self._thread_id
        if thread is None:
            return
        if thread_id is not None:
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None
        self._register_ok = False

    def _ensure_message_queue(self) -> None:
        """Create this thread's message queue before NULL-window hotkey registration."""
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._ensure_message_queue()
        flags = int(self._spec.modifiers) | MOD_NOREPEAT
        self._register_ok = bool(
            user32.RegisterHotKey(
                None,
                _HOTKEY_ID,
                flags,
                int(self._spec.virtual_key),
            )
        )
        self._registered.set()
        if not self._register_ok:
            return

        try:
            msg = wintypes.MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    self._tk_root.after(0, self._on_trigger)
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)


__all__ = [
    "GlobalHotkey",
    "HotkeySpec",
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "MOD_WIN",
]
