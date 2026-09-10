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

    def find_send_button(self, compose_box):
        """Locate the Send button next to the compose box (UIA).

        With text present, Telegram's compose-area button is the Send
        button; with an empty compose it is the MIC button. The injector
        only calls this when the compose verifiably still holds text.

        Scoring: a Button whose accessible name contains "send" wins;
        otherwise prefer buttons in the right half of/near the compose
        (the emoji button sits at the LEFT end, the send button at the
        right), then by distance. Returns None when nothing plausible is
        found — the caller treats that as a failed attempt, never a
        blind invoke.
        """
        hwnd = self.hwnd
        if not hwnd:
            return None
        try:
            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            window = app.window(handle=hwnd).wrapper_object()
            buttons = window.descendants(control_type="Button")
        except Exception:
            return None
        if not buttons:
            return None

        try:
            c = compose_box.rectangle()
        except Exception:
            return None
        c_cx = (c.left + c.right) / 2.0
        c_cy = (c.top + c.bottom) / 2.0

        candidates = []
        for button in buttons:
            try:
                r = button.rectangle()
                name = (button.element_info.name or "").lower()
            except Exception:
                continue
            # Must be horizontally adjacent to / overlapping the compose
            # area and vertically near it.
            if r.right < c.left - 20 or r.left > c.right + 240:
                continue
            if r.bottom < c.top - 20 or r.top > c.bottom + 20:
                continue
            center_x = (r.left + r.right) / 2.0
            center_y = (r.top + r.bottom) / 2.0
            distance = abs(center_x - c_cx) + abs(center_y - c_cy)
            named_send = "send" in name
            right_half = center_x >= c_cx
            candidates.append(((0 if named_send else 1,
                                0 if right_half else 1,
                                distance), button))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]
