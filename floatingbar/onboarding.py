"""Small first-run guide for the background-input workflow."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Optional

from . import ui_theme


_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
_MARKER_PATH = os.path.join(_APPDATA, "FloatingBar", "first-run-seen")


def marker_path() -> str:
    """Return the persistent first-run marker path."""
    return _MARKER_PATH


def has_seen() -> bool:
    """Return whether the first-run guide has already been dismissed."""
    try:
        return os.path.isfile(_MARKER_PATH)
    except OSError:
        return False


def mark_seen() -> None:
    """Persist dismissal without making startup dependent on disk access."""
    try:
        directory = os.path.dirname(_MARKER_PATH)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(_MARKER_PATH, "a", encoding="utf-8"):
            pass
    except OSError:
        pass


def show(parent: tk.Misc, *, force: bool = False) -> Optional[tk.Toplevel]:
    """Show the guide and return its window, or ``None`` when already seen."""
    if has_seen() and not force:
        return None

    window = tk.Toplevel(parent)
    window.title("Welcome to Floating Bar")
    window.resizable(False, False)
    window.transient(parent)
    window.attributes("-topmost", True)
    ui_theme.style_popup(window)

    frame = ui_theme.frame(window, padx=22, pady=18)
    frame.pack(fill="both", expand=True)

    ui_theme.label(frame, text="Welcome to Floating Bar", fg=ui_theme.TEXT_STRONG, font=("Segoe UI", 15, "bold")).pack(fill="x")
    tk.Label(
        frame,
        text="Reply into safe background targets without switching away from the work in front of you.",
        bg=ui_theme.SURFACE, fg=ui_theme.TEXT_MUTED, font=ui_theme.FONT_BODY, wraplength=340, justify="left",
    ).pack(anchor="w", pady=(4, 12))

    for step in (
        "1. Hover the orb to find safe background apps.",
        "2. Choose Type for editing or Chats when conversation selection is available.",
        "3. Enter your text and press Enter to submit without switching away.",
    ):
        tk.Label(
            frame, text=step, bg=ui_theme.SURFACE, fg=ui_theme.TEXT, font=ui_theme.FONT_BODY,
            wraplength=340, justify="left",
        ).pack(anchor="w", pady=2)

    tk.Label(
        frame,
        text="Privacy by default: background message bodies are not read. Only quick replies you explicitly save are stored locally.",
        bg=ui_theme.SURFACE, fg=ui_theme.TEXT_DIM, font=ui_theme.FONT_SMALL, wraplength=340, justify="left",
    ).pack(anchor="w", pady=(10, 14))

    def close() -> None:
        mark_seen()
        try:
            window.destroy()
        except tk.TclError:
            pass

    button = ui_theme.button(frame, text="Got it", command=close, primary=True)
    button.pack(anchor="e")
    window.bind("<Return>", lambda _event: (button.invoke(), "break")[1], add="+")
    window.bind("<Escape>", lambda _event: close(), add="+")
    button.focus_set()
    window.protocol("WM_DELETE_WINDOW", close)

    window.grab_set()
    window.update_idletasks()
    try:
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - window.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    return window


__all__ = ["has_seen", "marker_path", "mark_seen", "show"]
