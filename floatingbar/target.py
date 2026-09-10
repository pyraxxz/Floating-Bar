"""Locate the Telegram Desktop window and its message-compose box.

Window discovery: PROCESS IMAGE NAME first (telegram.exe / Telegram.exe
via EnumWindows) — the window title becomes the open chat's name and
usually contains no "Telegram", so title matching alone misses it. A
strict title fallback ("Telegram" / "Telegram Desktop") covers portable
installs that rename the exe.

Compose box: UI Automation descendants(control_type="Edit"), scored by
area with a bottom-half bonus and a read-only penalty. Telegram's search
box is small and near the top; the compose box is the wide Edit at the
bottom. There is no stable automation id for it — this heuristic is the
accepted fragility of the whole approach (see the spec).

No message content is ever read here — only geometry and control types.
"""

import re

import pywinauto
from pywinauto.findwindows import ElementNotFoundError

import config
from . import winapi


class TelegramNotFound(Exception):
    """Telegram Desktop (or its compose box) is not reachable."""


class TelegramTarget:
    """Cached Telegram window handle + compose-box finder."""

    def __init__(self):
        self._hwnd = None
        self._pid = None

    # -- window -------------------------------------------------------------

    @property
    def hwnd(self) -> int:
        """A currently-valid Telegram top-level hwnd, or 0. Re-scans when
        the cached handle dies (Telegram restarted, window closed...)."""
        if self._hwnd and winapi.user32.IsWindow(self._hwnd):
            return self._hwnd
        self.refresh()
        return self._hwnd or 0

    def is_available(self) -> bool:
        """Cheap check for status display (no UIA involved)."""
        return self.hwnd != 0

    def refresh(self) -> None:
        self._hwnd = None
        self._pid = None
        matches = winapi.find_windows(
            config.PROCESS_NAME_RE,
            title_re=config.TITLE_FALLBACK_RE,
        )
        if matches:
            self._hwnd, self._pid = matches[0][0], matches[0][1]

    # -- compose box ----------------------------------------------------------

    def compose_box(self):
        """Return the pywinauto UIA wrapper for Telegram's compose box.
        Raises TelegramNotFound if the window or a suitable Edit is gone."""
        hwnd = self.hwnd
        if not hwnd:
            raise TelegramNotFound(
                "Telegram Desktop doesn't seem to be running."
            )
        try:
            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            window = app.window(handle=hwnd).wrapper_object()
            edits = window.descendants(control_type="Edit")
        except (ElementNotFoundError, Exception) as e:
            # ElementNotFoundError: pywinauto couldn't wrap the handle;
            # bare Exception: comtypes COMError on stale elements.
            self._hwnd = None  # force a fresh scan next time
            raise TelegramNotFound(
                f"Could not read Telegram's window tree: {e}"
            ) from e

        if not edits:
            raise TelegramNotFound(
                "No editable control found — is a chat actually open?"
            )

        best, best_score = None, -1.0
        for edit in edits:
            score = self._score_compose_candidate(edit, window)
            if score > best_score:
                best, best_score = edit, score
        if best is None:
            raise TelegramNotFound("No usable compose box found.")
        return best

    @staticmethod
    def _score_compose_candidate(edit, window):
        """Bigger Edit wins; bottom-half wins; read-only loses hard."""
        try:
            rect = edit.rectangle()
            area = float(rect.width()) * float(rect.height())
            top = float(rect.top)
        except Exception:
            return -1.0

        score = area
        try:
            win_rect = window.rectangle()
            mid_y = (win_rect.top + win_rect.bottom) / 2.0
            if top >= mid_y:
                # Compose box lives in the bottom half; search lives on top.
                score *= 1.5
        except Exception:
            pass

        try:
            if edit.iface_value.CurrentIsReadOnly:
                return -1.0
        except Exception:
            pass  # no ValuePattern — can't tell, don't penalize

        return score

    def send_button_click(self, compose_box):
        """Locate the Send button and return (name, client_x, client_y).

        Client coordinates are computed from UIA rects (button center minus
        window origin) so both coordinate figures come from the SAME source
        and cannot disagree under DPI scaling. Telegram Desktop is a
        frameless window, so window origin ~ client origin.

        Layout logic: the compose row is [attach] [field] [emoji] [send |
        mic] — the rightmost button near the compose is the send button when
        text is present (and the mic button when it isn't). A button whose
        accessible name identifies it as a voice/mic control is returned
        but deprioritized, and the injector refuses to click it.

        Second pass: if no Button-typed control is found at all, look for
        any control named "*send*" near the compose (some Qt builds expose
        buttons with different control types).
        """
        hwnd = self.hwnd
        if not hwnd:
            return None
        try:
            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            window = app.window(handle=hwnd).wrapper_object()
            wrect = window.rectangle()
        except Exception:
            return None
        try:
            c = compose_box.rectangle()
        except Exception:
            return None
        c_cx = (c.left + c.right) / 2.0
        c_cy = (c.top + c.bottom) / 2.0

        def in_band(r):
            if r.right < c.left - 20 or r.left > c.right + 240:
                return False
            if r.bottom < c.top - 20 or r.top > c.bottom + 20:
                return False
            return True

        best = None  # (key, name, client_x, client_y)
        try:
            buttons = window.descendants(control_type="Button")
        except Exception:
            buttons = []
        for button in buttons:
            try:
                r = button.rectangle()
                name = (button.element_info.name or "")
            except Exception:
                continue
            if not in_band(r):
                continue
            center_x = (r.left + r.right) / 2.0
            center_y = (r.top + r.bottom) / 2.0
            lname = name.lower()
            named_send = "send" in lname
            named_voice = any(k in lname for k in
                              ("voice", "record", "mic", "audio"))
            if named_voice:
                key = (2, 0, 0.0)          # mic — reported, never preferred
            elif named_send:
                key = (0, 0, 0.0)          # explicit send — best possible
            else:
                # unnamed: rightmost button wins (emoji sits left of send)
                key = (1, -center_x,
                       abs(center_x - c_cx) + abs(center_y - c_cy))
            if best is None or key < best[0]:
                best = (key, name,
                        int(center_x - wrect.left),
                        int(center_y - wrect.top))
        if best is not None:
            return best[1], best[2], best[3]

        # Fallback: any control named "*send*" near the compose.
        try:
            for el in window.descendants():
                try:
                    name = (el.element_info.name or "")
                except Exception:
                    continue
                if "send" not in name.lower():
                    continue
                r = el.rectangle()
                if not in_band(r):
                    continue
                cx = int((r.left + r.right) / 2.0 - wrect.left)
                cy = int((r.top + r.bottom) / 2.0 - wrect.top)
                return name, cx, cy
        except Exception:
            pass
        return None
