"""Lightweight file trace — the app's black box recorder.

On every send attempt the injector records which strategy stage ran and
what it found (ValuePattern availability, verification results, button
names, focus outcomes). NEVER message content — only lengths, labels and
booleans.

The log lives in %APPDATA%\\FloatingBar\\trace.log and is truncated at
every app start, so it always holds just the current session.

Why this exists: the overlay is a blind injector on other people's
machines — when sending misbehaves on one specific Telegram build, this
log is the only way to see which stage of the cascade failed.
"""

import os
import time

_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
_DIR = os.path.join(_APPDATA, "FloatingBar")
_PATH = os.path.join(_DIR, "trace.log")


def dir_path() -> str:
    return _DIR


def path() -> str:
    return _PATH


def reset_session(version: str) -> None:
    """Truncate the log and write a session header."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_PATH, "w", encoding="utf-8") as f:
            f.write(f"=== Floating Bar {version} — session "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    except Exception:
        pass


def exception_name(exc: BaseException) -> str:
    """Return only an exception type name for content-free diagnostics."""
    name = type(exc).__name__
    return name if name.isidentifier() else "Exception"


def trace_exception(stage: str, exc: BaseException) -> None:
    """Trace an exception without recording its message text."""
    trace(f"{stage}: exception={exception_name(exc)}")


def trace(message: str) -> None:
    """Append one trace line. Best-effort: never raises into the caller."""
    try:
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')}  {message}\n")
    except Exception:
        pass


def section(title: str) -> None:
    trace("")
    trace(f"--- {title} ---")
