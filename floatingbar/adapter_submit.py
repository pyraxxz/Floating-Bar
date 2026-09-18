"""Central submission policy for non-Telegram background adapters.

Typing and submission are separate concerns even when an adapter currently
uses the same Win32 message path. The registry decides whether Enter is an
allowed submit mechanism. Production callers validate the mode before typing
so an unsupported adapter can never partially mutate a background composer.
"""

from . import winapi


_ALLOWED_MODES = frozenset({"enter"})


def _mode(spec) -> str:
    if spec is None:
        return "legacy-enter"
    return str(getattr(spec, "submit_mode", "") or "")


def validate_submission_mode(spec) -> str:
    """Return the effective submission mode or fail before any typing occurs."""
    mode = _mode(spec)
    if mode == "legacy-enter" or mode in _ALLOWED_MODES:
        return mode
    raise RuntimeError(f"background adapter submit mode is unsupported: {mode or 'unknown'}")


def submit_background_target(spec, target_hwnd: int, expected_pid: int = 0) -> str:
    """Submit an already-validated background target using its adapter policy."""
    if not target_hwnd:
        raise RuntimeError("background submission target is unavailable")
    mode = validate_submission_mode(spec)
    if mode in {"legacy-enter", "enter"}:
        if expected_pid:
            winapi.post_enter(target_hwnd, target=target_hwnd, expected_pid=expected_pid)
        else:
            winapi.post_enter(target_hwnd, target=target_hwnd)
        return "posted-enter (unverified)"
    raise RuntimeError(f"background adapter submit mode is unsupported: {mode}")


__all__ = ["submit_background_target", "validate_submission_mode"]
