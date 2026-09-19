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
from . import ui_theme

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
    """Small settings editor for non-content application preferences."""

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
        ui_theme.style_popup(self)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = ui_theme.frame(self, padx=20, pady=18)
        frame.pack(fill="both", expand=True)

        ui_theme.label(
            frame,
            text="Settings",
            fg=ui_theme.TEXT_STRONG,
            font=ui_theme.FONT_TITLE,
        ).pack(fill="x")
        ui_theme.label(
            frame,
            text="Choose how Floating Bar appears and how quickly it gets out of your way.",
            muted=True,
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(4, 14))

        startup_section = ui_theme.frame(
            frame,
            bg=ui_theme.SURFACE_ELEVATED,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            padx=12,
            pady=10,
        )
        startup_section.pack(fill="x", pady=(0, 10))
        ui_theme.label(
            startup_section,
            text="Startup",
            muted=True,
            bold=True,
            small=True,
        ).pack(fill="x")
        startup_var = tk.BooleanVar(value=startup.is_startup_enabled())
        self._startup_var = startup_var
        tk.Checkbutton(
            startup_section,
            text="Start Floating Bar with Windows",
            variable=startup_var,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            activebackground=ui_theme.SURFACE_ELEVATED,
            activeforeground=ui_theme.TEXT_STRONG,
            selectcolor=ui_theme.SURFACE,
            anchor="w",
            highlightthickness=0,
            font=ui_theme.FONT_BODY,
            cursor="hand2",
            takefocus=1,
        ).pack(fill="x", pady=(6, 2))
        ui_theme.label(
            startup_section,
            text="Keeps the orb ready after you sign in.",
            dim=True,
            small=True,
        ).pack(fill="x")

        input_section = ui_theme.frame(
            frame,
            bg=ui_theme.SURFACE_ELEVATED,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            padx=12,
            pady=10,
        )
        input_section.pack(fill="x", pady=(0, 10))

        ui_theme.label(
            input_section,
            text="Interaction",
            muted=True,
            bold=True,
            small=True,
        ).pack(fill="x")

        ui_theme.label(
            input_section,
            text="Summon hotkey",
            fg=ui_theme.TEXT,
            bold=True,
            small=True,
        ).pack(fill="x", pady=(8, 1))
        ui_theme.label(
            input_section,
            text="Restart Floating Bar after changing this shortcut.",
            dim=True,
            small=True,
        ).pack(fill="x", pady=(0, 4))

        hotkey_var = tk.StringVar(value=store.settings.summon_hotkey)
        self._hotkey_var = hotkey_var
        hotkey_menu = tk.OptionMenu(input_section, hotkey_var, *HOTKEY_OPTIONS.keys())
        hotkey_menu.configure(
            bg=ui_theme.SURFACE,
            fg=ui_theme.TEXT,
            activebackground=ui_theme.SURFACE_HOVER,
            activeforeground=ui_theme.TEXT_STRONG,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.ACCENT,
            relief="flat",
            bd=0,
            font=ui_theme.FONT_BODY,
            cursor="hand2",
        )
        hotkey_menu["menu"].configure(
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            activebackground=ui_theme.SURFACE_HOVER,
            activeforeground=ui_theme.TEXT_STRONG,
            font=ui_theme.FONT_BODY,
            borderwidth=0,
        )
        hotkey_menu.pack(fill="x")

        ui_theme.label(
            input_section,
            text="Collapse after inactivity",
            fg=ui_theme.TEXT,
            bold=True,
            small=True,
        ).pack(fill="x", pady=(10, 1))
        ui_theme.label(
            input_section,
            text="How long the expanded bar stays visible after typing.",
            dim=True,
            small=True,
        ).pack(fill="x", pady=(0, 2))

        seconds = max(2, min(15, store.idle_collapse_ms // 1000))
        self._seconds = tk.IntVar(value=seconds)
        scale = tk.Scale(
            input_section,
            from_=2,
            to=15,
            orient="horizontal",
            variable=self._seconds,
            resolution=1,
            showvalue=True,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            highlightthickness=0,
            troughcolor=ui_theme.SURFACE,
            activebackground=ui_theme.ACCENT_HOVER,
            bd=0,
            relief="flat",
            cursor="hand2",
        )
        scale.pack(fill="x", pady=(2, 0))

        self._status = ui_theme.label(
            frame,
            text="",
            muted=True,
            small=True,
            wraplength=390,
        )
        self._status.pack(fill="x", pady=(0, 8))

        buttons = ui_theme.frame(frame)
        buttons.pack(fill="x")
        ui_theme.button(
            buttons,
            text="Apply",
            command=self._apply,
            primary=True,
        ).pack(side="right", padx=(6, 0))
        ui_theme.button(
            buttons,
            text="Cancel",
            command=self.destroy,
            subtle=True,
        ).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy(), add="+")
        self.geometry("430x405")
        self.update_idletasks()
        self._center_on_parent(parent)

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            x = parent.winfo_rootx() + max(
                8,
                (parent.winfo_width() - self.winfo_width()) // 2,
            )
            y = parent.winfo_rooty() + max(
                8,
                (parent.winfo_height() - self.winfo_height()) // 2,
            )
            self.geometry(f"+{x}+{y}")
        except (tk.TclError, AttributeError):
            pass

    def _apply(self) -> None:
        startup_ok = startup.set_startup_enabled(bool(self._startup_var.get()))
        if startup.startup_supported() and not startup_ok:
            self._status.config(text="Startup could not be changed. No other settings were saved.")
            self._startup_var.set(startup.is_startup_enabled())
            return

        previous_hotkey = self.store.settings.summon_hotkey
        self.store.update_summon_hotkey(self._hotkey_var.get())
        settings = self.store.update_idle_collapse_ms(self._seconds.get())
        self.on_apply(settings)

        if previous_hotkey != settings.summon_hotkey:
            message = "Settings saved. Restart Floating Bar to activate the new summon hotkey."
        else:
            message = "Settings saved."
        self._status.config(text=message)
        self.after(700, self.destroy)


__all__ = ["AppSettings", "DEFAULT_HOTKEY", "HOTKEY_OPTIONS", "SettingsDialog", "SettingsStore", "hotkey_spec_for_name", "normalize_hotkey"]
