"""Raw Win32 bindings via ctypes.

Only what this app needs:

* locate the Telegram Desktop top-level window by PROCESS IMAGE NAME
  (title regexes are fragile — Telegram's title is the open chat's name
  and usually contains no "Telegram" at all)
* post WM_KEYDOWN / WM_KEYUP / WM_CHAR without stealing focus, with a
  properly constructed LPARAM (repeat count, scan code in bits 16-23,
  previous-state and transition bits for KEYUP). Zero-LPARAM key posts
  are known to be ignored by some Qt builds — Telegram is Qt.
* foreground-window capture / restore for the focus-stealing fallback
* hide the overlay from Alt-Tab (WS_EX_TOOLWINDOW)
* single-instance mutex
"""

import ctypes
import sys
import threading

if sys.platform != "win32":
    raise ImportError("floatingbar is Windows-only")

import ctypes.wintypes as wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

VK_CONTROL = 0x11
VK_RETURN = 0x0D

MAPVK_VK_TO_VSC = 0

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
SW_RESTORE = 9

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183

# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
user32.ShowWindow.restype = wintypes.BOOL

user32.GetWindowLongW.argtypes = [wintypes.HWND, wintypes.INT]
user32.GetWindowLongW.restype = wintypes.LONG

user32.SetWindowLongW.argtypes = [wintypes.HWND, wintypes.INT, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
user32.GetWindowTextW.restype = wintypes.INT

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL

# ---------------------------------------------------------------------------
# Window enumeration + process-name matching
# ---------------------------------------------------------------------------

def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def get_window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_process_image_name(pid: int) -> str:
    """Full path of the process image, or '' if it can't be queried."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def get_window_rect_area(hwnd: int) -> int:
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
    return 0


def _is_candidate_window(hwnd: int) -> bool:
    """Top-level, visible, titled, non-toolwindow."""
    if not user32.IsWindowVisible(hwnd):
        return False
    if not get_window_title(hwnd):
        return False
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if exstyle & WS_EX_TOOLWINDOW:
        return False
    return True


def _enum_windows() -> list:
    results = []

    @_WNDENUMPROC
    def _cb(hwnd, _lparam):
        results.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return results


def find_windows(process_re, title_re=None):
    """Return [(hwnd, pid, area, title, image_name)] for top-level windows whose
    process image matches `process_re`, or (if none matched and `title_re`
    is given) whose title matches `title_re`. Largest area first."""
    by_process = []
    by_title = []
    for hwnd in _enum_windows():
        if not _is_candidate_window(hwnd):
            continue
        pid = get_window_pid(hwnd)
        image = get_process_image_name(pid)
        base = image.rsplit("\\", 1)[-1] if image else ""
        title = get_window_title(hwnd)
        if process_re.search(base):
            by_process.append((hwnd, pid, get_window_rect_area(hwnd), title, base))
        elif title_re is not None and title_re.search(title):
            by_title.append((hwnd, pid, get_window_rect_area(hwnd), title, base))
    matches = by_process or by_title
    matches.sort(key=lambda m: m[2], reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Focus-free message posting
# ---------------------------------------------------------------------------

def _key_lparam(vk: int, up: bool) -> int:
    """WM_KEYDOWN/WM_KEYUP LPARAM per the Win32 contract:
    bits 0-15 repeat count (1), bits 16-23 scan code, bit 30 previous state,
    bit 31 transition state. A zero LPARAM is ignored by some Qt builds."""
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    lp = 1 | (scan << 16)
    if up:
        lp |= (1 << 30) | (1 << 31)
    return lp


def post_enter(hwnd: int, ctrl: bool = False) -> None:
    """Post an Enter keypress (optionally Ctrl+Enter) to a window's message
    queue WITHOUT changing focus or the foreground window."""
    if ctrl:
        user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, _key_lparam(VK_CONTROL, False))
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_RETURN, _key_lparam(VK_RETURN, False))
    user32.PostMessageW(hwnd, WM_KEYUP, VK_RETURN, _key_lparam(VK_RETURN, True))
    if ctrl:
        user32.PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, _key_lparam(VK_CONTROL, True))


def post_text(hwnd: int, text: str) -> None:
    """Post WM_CHAR for every UTF-16 code unit — surrogate-pair safe, so
    emoji and other astral characters survive injection."""
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        code_unit = data[i] | (data[i + 1] << 8)
        user32.PostMessageW(hwnd, WM_CHAR, code_unit, 0)


# ---------------------------------------------------------------------------
# Foreground helpers (focus-steal fallback path only)
# ---------------------------------------------------------------------------

def get_foreground_window() -> int:
    return user32.GetForegroundWindow() or 0


def set_foreground_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    return bool(user32.SetForegroundWindow(hwnd))


def ensure_restored(hwnd: int) -> None:
    if user32.IsWindow(hwnd) and user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)


# ---------------------------------------------------------------------------
# Overlay window tweaks
# ---------------------------------------------------------------------------

def hide_from_alt_tab(tk_child_hwnd: int) -> None:
    """Add WS_EX_TOOLWINDOW to the real top-level window so it never shows
    up in Alt-Tab (overrideredirect already removes the taskbar entry)."""
    root = user32.GetAncestor(tk_child_hwnd, GA_ROOT)
    if not root:
        root = tk_child_hwnd
    exstyle = user32.GetWindowLongW(root, GWL_EXSTYLE)
    user32.SetWindowLongW(root, GWL_EXSTYLE, exstyle | WS_EX_TOOLWINDOW)


# ---------------------------------------------------------------------------
# Single instance
# ---------------------------------------------------------------------------
_mutex_handle = None


def acquire_single_instance(name: str) -> bool:
    """True if we are the first instance; False if one is already running
    (we keep a module-level reference so the mutex stays alive)."""
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\" + name)
    if not _mutex_handle:
        return True  # can't tell — rather run than refuse
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
