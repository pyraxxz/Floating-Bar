"""Shared visual language and placement helpers for the Floating Bar UI.

This module contains only presentation helpers. It never discovers windows,
reads application content, or changes target-selection behavior.
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional, Sequence

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
        "takefocus": 1,
        "highlightthickness": 1,
        "highlightbackground": BORDER,
        "highlightcolor": ACCENT,
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


def adaptive_label_width(
    text: str,
    *,
    minimum: int = 66,
    maximum: int = 112,
    character_width: int = 7,
    padding: int = 8,
) -> int:
    """Estimate a bounded pixel width that keeps application labels readable."""
    cleaned = str(text or "").strip()
    minimum = max(1, int(minimum))
    maximum = max(minimum, int(maximum))
    character_width = max(1, int(character_width))
    padding = max(0, int(padding))
    estimated = len(cleaned) * character_width + padding
    return max(minimum, min(maximum, estimated))


def next_focus_index(current_index: int, count: int, direction: int) -> int:
    """Return a wrapped picker-row focus index without touching Tk state."""
    total = max(0, int(count))
    if total == 0:
        return -1
    step = 1 if int(direction) >= 0 else -1
    current = int(current_index)
    if current < 0 or current >= total:
        return 0 if step > 0 else total - 1
    return (current + step) % total


def bind_picker_navigation(
    window: tk.Toplevel,
    buttons: Sequence[tk.Button],
    *,
    on_escape,
) -> None:
    """Add predictable keyboard navigation to a picker without global focus hooks."""
    rows = tuple(buttons)
    if not rows:
        window.bind("<Escape>", lambda _event: on_escape(), add="+")
        return

    def move_focus(direction: int):
        current = window.focus_get()
        try:
            current_index = rows.index(current)
        except ValueError:
            current_index = -1
        rows[next_focus_index(current_index, len(rows), direction)].focus_set()

    def focus_edge(last: bool = False):
        rows[-1 if last else 0].focus_set()

    window.bind("<Up>", lambda _event: (move_focus(-1), "break")[1], add="+")
    window.bind("<Down>", lambda _event: (move_focus(1), "break")[1], add="+")
    window.bind("<Home>", lambda _event: (focus_edge(False), "break")[1], add="+")
    window.bind("<End>", lambda _event: (focus_edge(True), "break")[1], add="+")
    window.bind("<Escape>", lambda _event: (on_escape(), "break")[1], add="+")
    for row in rows:
        row.bind("<Up>", lambda _event: (move_focus(-1), "break")[1], add="+")
        row.bind("<Down>", lambda _event: (move_focus(1), "break")[1], add="+")
        row.bind("<Home>", lambda _event: (focus_edge(False), "break")[1], add="+")
        row.bind("<End>", lambda _event: (focus_edge(True), "break")[1], add="+")
    rows[0].focus_set()



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
        "takefocus": 1,
        "highlightthickness": 1,
        "highlightbackground": BORDER,
        "highlightcolor": ACCENT,
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
    "bind_picker_navigation",
    "next_focus_index",
    "style_popup",
]
