"""Small persistent settings surface for Floating Bar.

Only explicit application preferences are stored here. Background application
window titles, conversation names, message content, and UI Automation values
are never persisted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
import tkinter as tk
from pathlib import Path
from typing import Callable

from . import startup

_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
_DEFAULT_PATH = os.path.join(_APPDATA, "FloatingBar", "settings.json")
_SCHEMA_VERSION = 2

HOTKEY_OPTIONS = {
    "Ctrl+Alt+Space": (0x0002 | 0x0001, 0x20),
    "Ctrl+Shift+Space": (0x0002 | 0x0004, 0x20),
    "Alt+Shift+Space": (0x0001 | 0x0004, 0x20),
    "Ctrl+Alt+Enter": (0x0002 | 0x0001, 0x0D),
}
DEFAULT_HOTKEY = "Ctrl+Alt+Space"


def normalize_hotkey(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in HOTKEY_OPTIONS else DEFAULT_HOTKEY


def hotkey_spec_for_name(value: object) -> tuple[int, int]:
    return HOTKEY_OPTIONS[normalize_hotkey(value)]



@dataclass(frozen=True)
class AppSettings:
    idle_collapse_ms: int = 4000
    summon_hotkey: str = DEFAULT_HOTKEY

    @staticmethod
    def normalize_idle(value: object) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            seconds = 4
        seconds = max(2, min(15, seconds))
        return seconds * 1000


class SettingsStore:
    """Bounded local settings store using atomic replacement."""

    def __init__(self, path: str | None = None):
        self.path = str(path or _DEFAULT_PATH)
        self._settings = AppSettings()
        self._load()

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def idle_collapse_ms(self) -> int:
        return self._settings.idle_collapse_ms

    def update_idle_collapse_ms(self, value: object) -> AppSettings:
        normalized = AppSettings.normalize_idle(value)
        self._settings = AppSettings(
            idle_collapse_ms=normalized,
            summon_hotkey=self._settings.summon_hotkey,
        )
        self._save()
        return self._settings

    def update_summon_hotkey(self, value: object) -> AppSettings:
        normalized = normalize_hotkey(value)
        self._settings = AppSettings(
            idle_collapse_ms=self._settings.idle_collapse_ms,
            summon_hotkey=normalized,
        )
        self._save()
        return self._settings

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            return
        version = payload.get("version")
        if version not in {1, _SCHEMA_VERSION}:
            return
        self._settings = AppSettings(
            idle_collapse_ms=AppSettings.normalize_idle(payload.get("idle_collapse_seconds", 4)),
            summon_hotkey=(
                normalize_hotkey(payload.get("summon_hotkey", DEFAULT_HOTKEY))
                if version == _SCHEMA_VERSION
                else DEFAULT_HOTKEY
            ),
        )

    def _save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=".settings-",
                suffix=".tmp",
                dir=directory,
            )
            try:
                payload = {
                    "version": _SCHEMA_VERSION,
                    "idle_collapse_seconds": self._settings.idle_collapse_ms // 1000,
                    "summon_hotkey": self._settings.summon_hotkey,
                }
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        except OSError:
            pass


class SettingsDialog(tk.Toplevel):
    """Minimal settings editor for non-content application preferences."""

    def __init__(
        self,
        parent: tk.Misc,
        store: SettingsStore,
        on_apply: Callable[[AppSettings], None],
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_apply = on_apply
        self.title("Floating Bar settings")
        self.resizable(False, False)
        self.transient(parent)
        self.attributes("-topmost", True)
        self.configure(bg="#18181b")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = tk.Frame(self, bg="#18181b", padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        startup_var = tk.BooleanVar(value=startup.is_startup_enabled())
        self._startup_var = startup_var
        tk.Checkbutton(
            frame,
            text="Start Floating Bar with Windows",
            variable=startup_var,
            bg="#18181b",
            fg="#f4f4f5",
            activebackground="#18181b",
            activeforeground="#ffffff",
            selectcolor="#27272a",
            anchor="w",
            highlightthickness=0,
        ).pack(fill="x")

        tk.Label(
            frame,
            text="Summon hotkey (restart Floating Bar after changing)",
            bg="#18181b",
            fg="#d4d4d8",
            anchor="w",
        ).pack(fill="x", pady=(12, 2))

        hotkey_var = tk.StringVar(value=store.settings.summon_hotkey)
        self._hotkey_var = hotkey_var
        tk.OptionMenu(frame, hotkey_var, *HOTKEY_OPTIONS.keys()).pack(fill="x")

        tk.Label(
            frame,
            text="Collapse the expanded bar after inactivity",
            bg="#18181b",
            fg="#d4d4d8",
            anchor="w",
        ).pack(fill="x", pady=(12, 2))

        seconds = max(2, min(15, store.idle_collapse_ms // 1000))
        self._seconds = tk.IntVar(value=seconds)
        scale = tk.Scale(
            frame,
            from_=2,
            to=15,
            orient="horizontal",
            variable=self._seconds,
            resolution=1,
            showvalue=True,
            bg="#18181b",
            fg="#f4f4f5",
            highlightthickness=0,
            troughcolor="#27272a",
            activebackground="#52525b",
            bd=0,
        )
        scale.pack(fill="x")

        self._status = tk.Label(
            frame,
            text="",
            bg="#18181b",
            fg="#f59e0b",
            anchor="w",
        )
        self._status.pack(fill="x", pady=(4, 6))

        buttons = tk.Frame(frame, bg="#18181b")
        buttons.pack(fill="x", pady=(6, 0))
        tk.Button(
            buttons,
            text="Apply",
            command=self._apply,
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#f4f4f5",
        ).pack(side="right", padx=(6, 0))
        tk.Button(
            buttons,
            text="Close",
            command=self.destroy,
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#d4d4d8",
        ).pack(side="right")

        self.geometry("390x255")

    def _apply(self) -> None:
        startup_ok = startup.set_startup_enabled(bool(self._startup_var.get()))
        if startup.startup_supported() and not startup_ok:
            self._status.config(text="Startup setting could not be changed.")
            self._startup_var.set(startup.is_startup_enabled())
            return
        previous_hotkey = self.store.settings.summon_hotkey
        self.store.update_summon_hotkey(self._hotkey_var.get())
        settings = self.store.update_idle_collapse_ms(self._seconds.get())
        self.on_apply(settings)
        if previous_hotkey != settings.summon_hotkey:
            self._status.config(text="Settings applied. Restart to use the new summon hotkey.")
        else:
            self._status.config(text="Settings applied.")
        self.after(700, self.destroy)


__all__ = ["AppSettings", "DEFAULT_HOTKEY", "HOTKEY_OPTIONS", "SettingsDialog", "SettingsStore", "hotkey_spec_for_name", "normalize_hotkey"]
