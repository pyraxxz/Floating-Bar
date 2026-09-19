"""Shared visual language and placement helpers for the Floating Bar UI.

This module contains only presentation helpers. It never discovers windows,
reads application content, or changes target-selection behavior.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

SURFACE = "#18181b"
SURFACE_ELEVATED = "#202024"
SURFACE_HOVER = "#2a2a30"
SURFACE_PRESSED = "#34343b"
BORDER = "#3f3f46"
TEXT = "#f4f4f5"
TEXT_STRONG = "#ffffff"
TEXT_MUTED = "#a1a1aa"
TEXT_DIM = "#71717a"
ACCENT = "#60a5fa"
ACCENT_HOVER = "#93c5fd"
ACCENT_DIM = "#1e3a5f"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
ERROR = "#f87171"

FONT_BODY = ("Segoe UI", 9)
FONT_SMALL = ("Segoe UI", 8)
FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")
FONT_BODY_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 10, "bold")


def style_popup(window: tk.Toplevel, *, topmost: bool = True) -> None:
    """Apply consistent chrome to a transient borderless popup."""
    window.configure(bg=SURFACE)
    if topmost:
        window.attributes("-topmost", True)
    try:
        window.wm_attributes("-toolwindow", True)
    except Exception:
        pass


def frame(parent: tk.Misc, **kwargs) -> tk.Frame:
    """Create a theme-consistent dark frame."""
    options = {"bg": SURFACE, "bd": 0, "highlightthickness": 0}
    options.update(kwargs)
    return tk.Frame(parent, **options)


def label(
    parent: tk.Misc,
    text: str = "",
    *,
    muted: bool = False,
    dim: bool = False,
    bold: bool = False,
    **kwargs,
) -> tk.Label:
    """Create a themed label with predictable typography."""
    if dim:
        fg = TEXT_DIM
    elif muted:
        fg = TEXT_MUTED
    else:
        fg = TEXT_STRONG
    font = FONT_BODY_BOLD if bold else FONT_BODY
    if kwargs.pop("small", False):
        font = FONT_SMALL_BOLD if bold else FONT_SMALL
    options = {
        "text": text,
        "bg": SURFACE,
        "fg": fg,
        "font": font,
        "anchor": "w",
        "highlightthickness": 0,
        "bd": 0,
    }
    options.update(kwargs)
    return tk.Label(parent, **options)


def button(
    parent: tk.Misc,
    *,
    text: str,
    command=None,
    primary: bool = False,
    subtle: bool = False,
    width: Optional[int] = None,
    **kwargs,
) -> tk.Button:
    """Create a flat button with hover feedback and consistent spacing."""
    normal = ACCENT if primary else SURFACE_ELEVATED
    hover = ACCENT_HOVER if primary else SURFACE_HOVER
    fg = TEXT_STRONG if primary else TEXT
    options = {
        "text": text,
        "command": command,
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "bg": normal,
        "fg": fg,
        "activebackground": hover,
        "activeforeground": TEXT_STRONG,
        "disabledforeground": TEXT_DIM,
        "font": FONT_BODY_BOLD if primary else FONT_BODY,
        "cursor": "hand2",
    }
    if subtle:
        normal = SURFACE
        hover = SURFACE_HOVER
        options["bg"] = normal
    if width is not None:
        options["width"] = width
    options.update(kwargs)
    widget = tk.Button(parent, **options)

    def on_enter(_event=None):
        if str(widget.cget("state")) == "normal":
            widget.configure(bg=hover)

    def on_leave(_event=None):
        if str(widget.cget("state")) == "normal":
            widget.configure(bg=normal)

    widget.bind("<Enter>", on_enter, add="+")
    widget.bind("<Leave>", on_leave, add="+")
    return widget


def place_popup_near(
    owner: tk.Misc,
    popup: tk.Toplevel,
    width: int,
    height: int,
    *,
    gap: int = 8,
) -> tuple[int, int]:
    """Place a popup beside its owner while keeping it on-screen."""
    popup.update_idletasks()
    owner_x = owner.winfo_rootx()
    owner_y = owner.winfo_rooty()
    owner_w = owner.winfo_width()

    # Tk exposes the virtual desktop through vroot coordinates. Falling back
    # to the primary screen keeps lightweight tests and unusual Tk builds safe.
    try:
        origin_x = int(owner.winfo_vrootx())
        origin_y = int(owner.winfo_vrooty())
        desktop_w = int(owner.winfo_vrootwidth())
        desktop_h = int(owner.winfo_vrootheight())
    except (AttributeError, tk.TclError, TypeError, ValueError):
        origin_x = origin_y = 0
        desktop_w = int(owner.winfo_screenwidth())
        desktop_h = int(owner.winfo_screenheight())

    desktop_w = max(desktop_w, width + 16)
    desktop_h = max(desktop_h, height + 16)
    right_edge = origin_x + desktop_w
    bottom_edge = origin_y + desktop_h

    x_right = owner_x + owner_w + gap
    x_left = owner_x - width - gap
    if x_right + width <= right_edge:
        x = x_right
    else:
        x = x_left
    x = max(origin_x + 8, min(x, right_edge - width - 8))

    y = max(origin_y + 8, min(owner_y, bottom_edge - height - 8))
    return x, y


def row_button(
    parent: tk.Misc,
    *,
    text: str,
    command=None,
    selected: bool = False,
    attention: bool = False,
    disabled: bool = False,
    width: Optional[int] = None,
) -> tk.Button:
    """Create a picker row with clear selection/attention affordances."""
    if disabled:
        normal = SURFACE
        hover = SURFACE
        fg = TEXT_DIM
        cursor = "arrow"
    elif selected:
        normal = ACCENT_DIM
        hover = "#294e7a"
        fg = TEXT_STRONG
        cursor = "hand2"
    elif attention:
        normal = "#352b12"
        hover = "#4a3b14"
        fg = "#fde68a"
        cursor = "hand2"
    else:
        normal = SURFACE
        hover = SURFACE_HOVER
        fg = TEXT
        cursor = "hand2"

    options = {
        "text": text,
        "command": command,
        "anchor": "w",
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "bg": normal,
        "fg": fg,
        "activebackground": hover,
        "activeforeground": TEXT_STRONG,
        "disabledforeground": TEXT_DIM,
        "state": "disabled" if disabled else "normal",
        "font": FONT_BODY_BOLD if selected or attention else FONT_BODY,
        "cursor": cursor,
    }
    if width is not None:
        options["width"] = width
    widget = tk.Button(parent, **options)

    def on_enter(_event=None):
        if not disabled:
            widget.configure(bg=hover)

    def on_leave(_event=None):
        if not disabled:
            widget.configure(bg=normal)

    widget.bind("<Enter>", on_enter, add="+")
    widget.bind("<Leave>", on_leave, add="+")
    return widget


__all__ = [
    "ACCENT",
    "ACCENT_DIM",
    "ACCENT_HOVER",
    "BORDER",
    "ERROR",
    "FONT_BODY",
    "FONT_BODY_BOLD",
    "FONT_SMALL",
    "FONT_SMALL_BOLD",
    "FONT_TITLE",
    "SURFACE",
    "SURFACE_ELEVATED",
    "SURFACE_HOVER",
    "SURFACE_PRESSED",
    "SUCCESS",
    "TEXT",
    "TEXT_DIM",
    "TEXT_MUTED",
    "TEXT_STRONG",
    "WARNING",
    "button",
    "frame",
    "label",
    "place_popup_near",
    "row_button",
    "style_popup",
]
