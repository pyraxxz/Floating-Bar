"""Raw Win32 bindings via ctypes.

Only what this app needs:

* locate the Telegram Desktop top-level window by PROCESS IMAGE NAME
* post keyboard/mouse messages without changing foreground focus
* foreground-window capture / restore for the opt-in fallback
* hide the overlay from Alt-Tab
* single-instance mutex
"""

import ctypes
import sys
import time

if sys.platform != "win32":
    raise ImportError("floatingbar is Windows-only")

import ctypes.wintypes as wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

VK_CONTROL = 0x11
VK_RETURN = 0x0D
MAPVK_VK_TO_VSC = 0

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
SW_RESTORE = 9

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183

# GetWindowThreadProcessId can briefly report no PID while a GUI window is
# being recreated. A tiny bounded retry avoids treating that transient state
# as a target-process replacement while still failing closed when the window
# really disappears.
_WINDOW_PID_READ_RETRIES = 3
_WINDOW_PID_READ_DELAY_S = 0.01

user32.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
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
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextW.argtypes = [
    wintypes.HWND, wintypes.LPWSTR, wintypes.INT
]
user32.GetWindowTextW.restype = wintypes.INT
user32.GetWindowRect.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.RECT)
]
user32.GetWindowRect.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [
    wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.CreateMutexW.argtypes = [
    wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR
]
kernel32.CreateMutexW.restype = wintypes.HANDLE


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.GetGUIThreadInfo.argtypes = [
    wintypes.DWORD, ctypes.POINTER(_GUITHREADINFO)
]
user32.GetGUIThreadInfo.restype = wintypes.BOOL
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def get_window_pid(hwnd: int) -> int:
    """Return a window's PID, tolerating brief zero-PID GUI transitions."""
    if not hwnd:
        return 0
    for attempt in range(_WINDOW_PID_READ_RETRIES):
        pid = wintypes.DWORD(0)
        try:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        except Exception:
            pid.value = 0
        if pid.value:
            return int(pid.value)
        if attempt < _WINDOW_PID_READ_RETRIES - 1:
            time.sleep(_WINDOW_PID_READ_DELAY_S)
    return 0

def get_window_class_name(hwnd: int) -> str:
    """Return the top-level Win32 class name without reading window content."""
    if not hwnd or not user32.IsWindow(hwnd):
        return ""
    try:
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
        user32.GetClassNameW.restype = wintypes.INT
        buf = ctypes.create_unicode_buffer(256)
        length = user32.GetClassNameW(hwnd, buf, len(buf))
        return buf.value[: max(0, int(length))]
    except Exception:
        return ""


def get_process_image_name(pid: int) -> str:
    """Full path of the process image, or '' if it can't be queried."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)
        ):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def get_process_creation_time(pid: int) -> int | None:
    """Return a content-free process-start timestamp, or ``None`` if unavailable."""
    if not pid:
        return None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
    except Exception:
        return None
    finally:
        kernel32.CloseHandle(handle)


def get_window_rect_area(hwnd: int) -> int:
    rect = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
    return 0


def _is_candidate_window(hwnd: int) -> bool:
    """Top-level, visible, non-toolwindow; a title is not required."""
    if not user32.IsWindowVisible(hwnd):
        return False
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return not (exstyle & WS_EX_TOOLWINDOW)


def _enum_windows() -> list:
    results = []

    @_WNDENUMPROC
    def _cb(hwnd, _lparam):
        results.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return results


def find_windows(process_re, title_re=None):
    """Return matching top-level windows, largest first."""
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
            by_process.append(
                (hwnd, pid, get_window_rect_area(hwnd), title, base)
            )
        elif title_re is not None and title_re.search(title):
            by_title.append(
                (hwnd, pid, get_window_rect_area(hwnd), title, base)
            )
    matches = by_process or by_title
    matches.sort(key=lambda m: m[2], reverse=True)
    return matches


def _key_lparam(vk: int, up: bool) -> int:
    """WM_KEYDOWN/WM_KEYUP LPARAM per the Win32 contract."""
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    lp = 1 | (scan << 16)
    if up:
        lp |= (1 << 30) | (1 << 31)
    return lp


def _post(
    hwnd: int,
    message: int,
    wparam: int,
    lparam: int,
    label: str,
    expected_pid: int = 0,
    expected_process_start: int | None = None,
) -> None:
    """Post one message after rechecking exact HWND/PID/process-start identity."""
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError(f"{label}: target window is invalid")
    if expected_pid and get_window_pid(hwnd) != int(expected_pid):
        raise RuntimeError(f"{label}: target window process changed")
    if expected_pid and expected_process_start is not None:
        current_process_start = get_process_creation_time(int(expected_pid))
        if current_process_start is None:
            raise RuntimeError(f"{label}: target process identity unavailable")
        if current_process_start != int(expected_process_start):
            raise RuntimeError(f"{label}: target process instance changed")
    if not user32.PostMessageW(hwnd, message, wparam, lparam):
        error = ctypes.get_last_error()
        raise RuntimeError(
            f"{label}: PostMessageW failed (last_error={error})"
        )


def get_focused_hwnd(hwnd: int) -> int:
    """Return the child HWND currently holding focus, when available."""
    try:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(_GUITHREADINFO)
        if tid and user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            focused = info.hwndFocus or 0
            if focused and user32.IsWindow(focused):
                return focused
    except Exception:
        pass
    return hwnd


def post_enter(
    hwnd: int,
    ctrl: bool = False,
    target: int = 0,
    expected_pid: int = 0,
    expected_process_start: int | None = None,
) -> None:
    """Post an Enter keypress without changing foreground focus.

    ``target`` may pin the exact child HWND already validated by the caller;
    otherwise the current focused child is resolved from ``hwnd`` as before.
    """
    target = target or get_focused_hwnd(hwnd) or hwnd
    char_code = 0x0A if ctrl else 0x0D
    if ctrl:
        _post(
            target, WM_KEYDOWN, VK_CONTROL,
            _key_lparam(VK_CONTROL, False), "Ctrl keydown", expected_pid,
            expected_process_start,
        )
    _post(
        target, WM_KEYDOWN, VK_RETURN,
        _key_lparam(VK_RETURN, False), "Enter keydown", expected_pid,
        expected_process_start,
    )
    _post(
        target, WM_CHAR, char_code,
        _key_lparam(VK_RETURN, False), "Enter char", expected_pid,
        expected_process_start,
    )
    _post(
        target, WM_KEYUP, VK_RETURN,
        _key_lparam(VK_RETURN, True), "Enter keyup", expected_pid,
        expected_process_start,
    )
    if ctrl:
        _post(
            target, WM_KEYUP, VK_CONTROL,
            _key_lparam(VK_CONTROL, True), "Ctrl keyup", expected_pid,
            expected_process_start,
        )


def _utf16_code_units(text: str) -> list[int]:
    """Return the UTF-16LE code units that Win32 WM_CHAR expects."""
    data = text.encode("utf-16-le")
    return [
        data[i] | (data[i + 1] << 8)
        for i in range(0, len(data), 2)
    ]


def post_text(
    hwnd: int,
    text: str,
    expected_pid: int = 0,
    expected_process_start: int | None = None,
) -> None:
    """Post UTF-16 code units and fail if any message is rejected."""
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError("WM_CHAR text post: target window is invalid")
    for code_unit in _utf16_code_units(text):
        _post(
            hwnd,
            WM_CHAR,
            code_unit,
            0,
            "WM_CHAR text post",
            expected_pid,
            expected_process_start,
        )


def post_click(
    hwnd: int,
    client_x: int,
    client_y: int,
    expected_pid: int = 0,
    expected_process_start: int | None = None,
) -> None:
    """Post a background left click without moving the real mouse."""
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError("mouse click post: target window is invalid")
    lparam = ((client_y & 0xFFFF) << 16) | (client_x & 0xFFFF)
    _post(hwnd, WM_MOUSEMOVE, 0, lparam, "mouse move", expected_pid, expected_process_start)
    _post(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam, "mouse down", expected_pid, expected_process_start)
    _post(hwnd, WM_LBUTTONUP, 0, lparam, "mouse up", expected_pid, expected_process_start)


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd) and user32.IsIconic(hwnd))


def get_foreground_window() -> int:
    return user32.GetForegroundWindow() or 0


def set_foreground_window(hwnd: int) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    return bool(user32.SetForegroundWindow(hwnd))


def ensure_restored(hwnd: int) -> None:
    if user32.IsWindow(hwnd) and user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)


def hide_from_alt_tab(tk_child_hwnd: int) -> None:
    """Add WS_EX_TOOLWINDOW to the real top-level window."""
    root = user32.GetAncestor(tk_child_hwnd, GA_ROOT) or tk_child_hwnd
    exstyle = user32.GetWindowLongW(root, GWL_EXSTYLE)
    user32.SetWindowLongW(root, GWL_EXSTYLE, exstyle | WS_EX_TOOLWINDOW)


_mutex_handle = None


def acquire_single_instance(name: str) -> bool:
    """True if this is the first instance; False if one already exists."""
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, False, "Local\\" + name)
    if not _mutex_handle:
        return True
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
