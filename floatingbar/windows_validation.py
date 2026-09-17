"""Content-free Windows validation snapshot helpers.

The validation snapshot records only machine/runtime capability information:
OS/build, Python/runtime architecture, monitor count, DPI-awareness state, and
which supported application processes currently expose user-facing windows.
It never reads or stores window titles, conversation names, message bodies,
input values, or clipboard contents.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import ctypes
import platform
import sys
from typing import Iterable, Mapping

from .app_adapters import AppAdapterSpec
from .background_windows import enumerate_background_windows
from .dpi import enable_per_monitor_awareness


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AdapterObservation:
    key: str
    label: str
    known_processes: tuple[str, ...]
    open_window_count: int
    observed_processes: tuple[str, ...]
    observed_versions: tuple[str, ...] = ()


@dataclass(frozen=True)
class WindowsValidationSnapshot:
    schema_version: int
    platform: str
    windows_release: str
    windows_version: str
    windows_service_pack: str
    architecture: str
    python_version: str
    monitor_count: int
    dpi_awareness: str
    observed_window_count: int
    adapters: tuple[AdapterObservation, ...]

    def to_dict(self) -> dict:
        """Return a JSON-safe, content-free representation."""
        return {
            "schema_version": self.schema_version,
            "platform": self.platform,
            "windows_release": self.windows_release,
            "windows_version": self.windows_version,
            "windows_service_pack": self.windows_service_pack,
            "architecture": self.architecture,
            "python_version": self.python_version,
            "monitor_count": self.monitor_count,
            "dpi_awareness": self.dpi_awareness,
            "observed_window_count": self.observed_window_count,
            "adapters": [
                {
                    "key": item.key,
                    "label": item.label,
                    "known_processes": list(item.known_processes),
                    "open_window_count": item.open_window_count,
                    "observed_processes": list(item.observed_processes),
                    "observed_versions": list(item.observed_versions),
                }
                for item in self.adapters
            ],
        }


def _monitor_count() -> int:
    """Return the Windows-reported monitor count without enumerating content."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        count = int(user32.GetSystemMetrics(80))  # SM_CMONITORS
        return max(0, count)
    except Exception:
        return 0


def _dpi_awareness() -> str:
    """Return the current process DPI-awareness mode after bootstrap attempt."""
    try:
        enable_per_monitor_awareness()
    except Exception:
        pass

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        get_awareness = getattr(shcore, "GetProcessDpiAwareness", None)
        if get_awareness is None:
            return "unknown"
        get_awareness.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        get_awareness.restype = ctypes.c_long
        value = ctypes.c_int(-1)
        result = int(get_awareness(None, ctypes.byref(value)))
        if result != 0:
            return "unknown"
        return {
            0: "unaware",
            1: "system",
            2: "per-monitor",
        }.get(int(value.value), "unknown")
    except Exception:
        return "unknown"


def _adapter_specs() -> tuple[AppAdapterSpec, ...]:
    """Return known registry adapters once, preserving registry order."""
    from .app_adapters import _ADAPTERS

    return tuple(_ADAPTERS)


def _process_file_version(path: str) -> str:
    """Return an executable's file-product version without reading UI content."""
    if sys.platform != "win32" or not path:
        return ""
    try:
        import win32api

        info = win32api.GetFileVersionInfo(path, "\\")
        ms = int(info.get("FileVersionMS", 0))
        ls = int(info.get("FileVersionLS", 0))
        parts = (
            (ms >> 16) & 0xFFFF,
            ms & 0xFFFF,
            (ls >> 16) & 0xFFFF,
            ls & 0xFFFF,
        )
        return ".".join(str(part) for part in parts)
    except Exception:
        return ""


def _observe_adapters(
    processes: Iterable[str],
    versions: Mapping[str, Iterable[str]] | None = None,
) -> tuple[AdapterObservation, ...]:
    counts = Counter(str(name).casefold() for name in processes if name)
    normalized_versions = {
        str(name).casefold(): tuple(
            sorted({str(version).strip() for version in values if str(version).strip()})
        )
        for name, values in (versions or {}).items()
    }
    result = []
    for spec in _adapter_specs():
        aliases = tuple(process.casefold() for process in spec.processes)
        matching = tuple(name for name in aliases if counts.get(name, 0) > 0)
        observed_versions = tuple(
            version
            for name in matching
            for version in normalized_versions.get(name, ())
        )
        result.append(
            AdapterObservation(
                key=spec.key,
                label=spec.label,
                known_processes=aliases,
                open_window_count=sum(counts.get(name, 0) for name in aliases),
                observed_processes=matching,
                observed_versions=tuple(dict.fromkeys(observed_versions)),
            )
        )
    return tuple(result)


def capture_snapshot() -> WindowsValidationSnapshot:
    """Capture a content-free snapshot of the current Windows test environment."""
    if sys.platform != "win32":
        raise RuntimeError("Windows validation is only supported on Windows")

    release, version, service_pack = platform.win32_ver()
    versions: dict[str, set[str]] = {}
    try:
        windows = enumerate_background_windows(include_minimized=True)
        process_names = tuple(item.process_name for item in windows)
        for item in windows:
            image_path = ""
            try:
                from . import winapi

                image_path = winapi.get_process_image_name(item.pid)
            except Exception:
                pass
            file_version = _process_file_version(image_path or "")
            if file_version:
                versions.setdefault(item.process_name.casefold(), set()).add(file_version)
        observed_window_count = len(windows)
    except Exception:
        process_names = ()
        observed_window_count = 0

    return WindowsValidationSnapshot(
        schema_version=SCHEMA_VERSION,
        platform=platform.system() or "Windows",
        windows_release=release or "",
        windows_version=version or "",
        windows_service_pack=service_pack or "",
        architecture=platform.machine() or "",
        python_version=platform.python_version(),
        monitor_count=_monitor_count(),
        dpi_awareness=_dpi_awareness(),
        observed_window_count=observed_window_count,
        adapters=_observe_adapters(process_names, versions),
    )


def format_report(snapshot: WindowsValidationSnapshot) -> str:
    """Format a stable human-readable validation summary."""
    lines = [
        "Floating Bar Windows validation snapshot",
        f"  schema_version={snapshot.schema_version}",
        f"  platform={snapshot.platform}",
        f"  windows_release={snapshot.windows_release or 'unknown'}",
        f"  windows_version={snapshot.windows_version or 'unknown'}",
        f"  windows_service_pack={snapshot.windows_service_pack or 'none'}",
        f"  architecture={snapshot.architecture or 'unknown'}",
        f"  python_version={snapshot.python_version}",
        f"  monitor_count={snapshot.monitor_count}",
        f"  dpi_awareness={snapshot.dpi_awareness}",
        f"  observed_window_count={snapshot.observed_window_count}",
        "  adapters:",
    ]
    for adapter in snapshot.adapters:
        observed = ",".join(adapter.observed_processes) or "none"
        versions = ",".join(adapter.observed_versions) or "unknown"
        lines.append(
            f"    - {adapter.label}: open_window_count={adapter.open_window_count} "
            f"observed_processes={observed} versions={versions}"
        )
    return "\n".join(lines)


__all__ = [
    "AdapterObservation",
    "SCHEMA_VERSION",
    "WindowsValidationSnapshot",
    "capture_snapshot",
    "format_report",
]
