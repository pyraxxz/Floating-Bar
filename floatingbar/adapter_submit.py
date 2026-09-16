"""Central submission policy for non-Telegram background adapters.

Typing and submission are separate concerns even when an adapter currently
uses the same Win32 message path. The registry decides whether Enter is an
allowed submit mechanism. The ``None`` policy is retained only for direct
legacy target callers; production routing always binds an explicit adapter.
"""

from . import winapi


_ALLOWED_MODES = frozenset({"enter"})


def submit_background_target(spec, target_hwnd: int) -> str:
    """Submit an already-validated background target using its adapter policy."""
    if not target_hwnd:
        raise RuntimeError("background submission target is unavailable")

    if spec is None:
        winapi.post_enter(target_hwnd, target=target_hwnd)
        return "posted-enter (unverified)"

    mode = getattr(spec, "submit_mode", "")
    if mode in _ALLOWED_MODES:
        winapi.post_enter(target_hwnd, target=target_hwnd)
        return "posted-enter (unverified)"

    raise RuntimeError(f"background adapter submit mode is unsupported: {mode or 'unknown'}")


__all__ = ["submit_background_target"]
