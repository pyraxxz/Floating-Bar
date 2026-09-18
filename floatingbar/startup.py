"""Windows per-user startup registration for Floating Bar.

The startup entry is intentionally scoped to HKCU and requires no elevation.
It points to the current executable when packaged, or to the current Python
interpreter plus script when running from source.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

try:
    import winreg  # type: ignore
except ImportError:  # pragma: no cover - exercised on non-Windows hosts.
    winreg = None  # type: ignore

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "FloatingBar"


def startup_supported() -> bool:
    return sys.platform == "win32" and winreg is not None


def startup_command(*, executable: str | None = None, script: str | None = None, frozen: bool | None = None) -> str:
    """Return a safe command line for the per-user Run key."""
    exe = str(executable or sys.executable)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    if is_frozen:
        argv = [exe]
    else:
        entry = Path(script or (sys.argv[0] if sys.argv else "main.py")).resolve()
        argv = [exe, os.fspath(entry)]
    return subprocess.list2cmdline(argv)


def is_startup_enabled() -> bool:
    if not startup_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, _RUN_VALUE)
            return bool(str(value).strip())
    except (OSError, FileNotFoundError):
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Enable/disable the HKCU startup entry; return whether the requested state is applied."""
    if not startup_supported():
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                command = startup_command()
                winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE)
                except FileNotFoundError:
                    pass
        return is_startup_enabled() is bool(enabled)
    except OSError:
        return False


__all__ = ["is_startup_enabled", "set_startup_enabled", "startup_command", "startup_supported"]
