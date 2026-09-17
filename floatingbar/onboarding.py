"""Small first-run guide for the background-input workflow."""

from __future__ import annotations

import os
import tkinter as tk
from typing import Optional


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
    window.title("Floating Bar")
    window.resizable(False, False)
    window.transient(parent)
    window.attributes("-topmost", True)
    window.configure(bg="#18181b")

    frame = tk.Frame(window, bg="#18181b", padx=18, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Floating Bar", bg="#18181b", fg="#ffffff", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(
        frame,
        text="Send into background apps without switching away from your work.",
        bg="#18181b", fg="#d4d4d8", font=("Segoe UI", 9), wraplength=340, justify="left",
    ).pack(anchor="w", pady=(4, 12))

    for step in (
        "1. Hover the orb to see safe background apps.",
        "2. Choose an app, then choose Type or Chats.",
        "3. Enter your text and press Enter to submit.",
    ):
        tk.Label(
            frame, text=step, bg="#18181b", fg="#f4f4f5", font=("Segoe UI", 9),
            wraplength=340, justify="left",
        ).pack(anchor="w", pady=2)

    tk.Label(
        frame,
        text="The bar does not read message contents from background apps.",
        bg="#18181b", fg="#a1a1aa", font=("Segoe UI", 8), wraplength=340, justify="left",
    ).pack(anchor="w", pady=(10, 14))

    def close() -> None:
        mark_seen()
        try:
            window.destroy()
        except tk.TclError:
            pass

    window.protocol("WM_DELETE_WINDOW", close)
    tk.Button(
        frame, text="Got it", command=close, relief="flat", bd=0, padx=14, pady=6,
        bg="#27272a", fg="#ffffff", activebackground="#3f3f46", activeforeground="#ffffff",
    ).pack(anchor="e")

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
