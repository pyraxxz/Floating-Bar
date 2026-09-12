"""Windows DPI-awareness bootstrap for reliable cross-monitor coordinates."""

import ctypes
import sys

from . import trace


# PROCESS_PER_MONITOR_DPI_AWARE for the legacy Shcore API.
_PROCESS_PER_MONITOR_DPI_AWARE = 2
# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 is (void*)-4.
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def enable_per_monitor_awareness() -> bool:
    """Opt into per-monitor-V2 DPI awareness before creating Tk windows.

    Returns True when Windows accepts either the modern context API or the
    legacy Shcore fallback. A failure is intentionally non-fatal: older or
    restricted environments can still run with their existing DPI behavior.
    """
    if sys.platform != "win32":
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if setter is not None:
            setter.argtypes = [ctypes.c_void_p]
            setter.restype = ctypes.c_bool
            if setter(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
                trace.trace("DPI: per-monitor-V2 awareness enabled")
                return True
            trace.trace(
                f"DPI: SetProcessDpiAwarenessContext rejected "
                f"request (last_error={ctypes.get_last_error()})"
            )
    except Exception as exc:
        trace.trace(f"DPI: modern awareness API unavailable: {exc}")

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        setter = getattr(shcore, "SetProcessDpiAwareness", None)
        if setter is not None:
            setter.argtypes = [ctypes.c_int]
            setter.restype = ctypes.c_long
            result = int(setter(_PROCESS_PER_MONITOR_DPI_AWARE))
            if result == 0:
                trace.trace("DPI: per-monitor awareness enabled via Shcore")
                return True
            # E_ACCESSDENIED means the process is already DPI-aware; that is
            # still a valid final state for our coordinate calculations.
            if result == 0x80070005:
                trace.trace("DPI: process was already DPI-aware")
                return True
            trace.trace(f"DPI: Shcore SetProcessDpiAwareness returned {result:#x}")
    except Exception as exc:
        trace.trace(f"DPI: legacy awareness API unavailable: {exc}")

    return False
