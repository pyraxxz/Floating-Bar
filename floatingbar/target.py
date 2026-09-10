"""Locate the Telegram window, its compose box, and the Send button.

Window discovery: PROCESS IMAGE NAME first (telegram.exe / Telegram.exe
via EnumWindows) — the window title becomes the open chat's name and
usually contains no "Telegram", so title matching alone misses it. A
strict title fallback ("Telegram" / "Telegram Desktop") covers portable
installs that rename the exe.

Compose box: UI Automation descendants(control_type="Edit"), scored by
area with a bottom-half bonus and a read-only penalty. Telegram's search
box is small and near the top; the compose box is the wide Edit at the
bottom.

v0.1.5 additions driven by real trace data (a build whose accessibility
reads never reflect the text that is visibly in the field):

* compose_click_point / control_click_point — posted-click targets in
  client coordinates (DPI-consistent: both rects from the same source).
* edit_audit — after landing text, enumerate EVERY Edit control and
  report value LENGTHS only (never content — R10), so the trace shows
  where the text actually landed and whether any read channel reflects
  it.
* send_button_click — search band around the text-holding Edit, with a
  window-bottom band fallback (the compose row lives in the bottom
  strip even when the Edit geometry is unreliable).
"""

import re

import pywinauto
from pywinauto.findwindows import ElementNotFoundError

import config
from . import trace
from . import winapi


class _Band:
    """Minimal rect-like search band."""
    def __init__(self, left, top, right, bottom):
        self.left, self.top = left, top
        self.right, self.bottom = right, bottom


class TelegramNotFound(Exception):
    """Telegram Desktop (or its compose box) is not reachable."""


class TelegramTarget:
    """Cached Telegram window handle + compose-box finder."""

    def __init__(self):
        self._hwnd = None
        self._pid = None
        # Runtime id of the CONFIRMED real compose field (v0.1.6: Telegram's
        # compose is two nested Edits — a wrapper whose reads are always
        # empty, and the inner field that actually holds the text). Once the
        # audit confirms the inner one, prefer it on every later send.
        self._preferred_rid = None

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

    # -- window wrapper --------------------------------------------------------

    def _window(self):
        hwnd = self.hwnd
        if not hwnd:
            raise TelegramNotFound(
                "Telegram Desktop doesn't seem to be running."
            )
        app = pywinauto.Application(backend="uia").connect(handle=hwnd)
        return app.window(handle=hwnd).wrapper_object()

    # -- compose box ----------------------------------------------------------

    def compose_box(self):
        """Return the pywinauto UIA wrapper for Telegram's compose box.
        Raises TelegramNotFound if the window or a suitable Edit is gone.
        Traces every Edit candidate's geometry (never content)."""
        try:
            window = self._window()
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

        if self._preferred_rid is not None:
            for edit in edits:
                try:
                    if tuple(edit.element_info.runtime_id) ==                             tuple(self._preferred_rid):
                        trace.trace("compose: using remembered inner field")
                        return edit
                except Exception:
                    continue

        for i, edit in enumerate(edits):
            try:
                r = edit.rectangle()
                trace.trace(f"edit[{i}] rect=({r.left},{r.top})-"
                            f"({r.right},{r.bottom}) "
                            f"{r.width()}x{r.height()}")
            except Exception:
                trace.trace(f"edit[{i}] rect unreadable")

        best, best_score = None, -1.0
        for edit in edits:
            score = self._score_compose_candidate(edit, window)
            if score > best_score:
                best, best_score = edit, score
        if best is None:
            raise TelegramNotFound("No usable compose box found.")
        try:
            r = best.rectangle()
            trace.trace(f"compose chosen: ({r.left},{r.top})-"
                        f"({r.right},{r.bottom})")
        except Exception:
            pass
        return best

    @staticmethod
    def _score_compose_candidate(edit, window):
        """Bigger Edit wins; bottom-quarter wins harder; read-only loses."""
        try:
            rect = edit.rectangle()
            area = float(rect.width()) * float(rect.height())
            top = float(rect.top)
        except Exception:
            return -1.0

        score = area
        try:
            win_rect = window.rectangle()
            win_h = float(win_rect.bottom - win_rect.top)
            # The compose row lives in the bottom quarter of the window;
            # the search field lives at the top. Weight accordingly.
            if top >= win_rect.bottom - 0.25 * win_h:
                score *= 2.0
            elif top >= (win_rect.top + win_rect.bottom) / 2.0:
                score *= 1.5
        except Exception:
            pass

        try:
            if edit.iface_value.CurrentIsReadOnly:
                return -1.0
        except Exception:
            pass  # no ValuePattern — can't tell, don't penalize

        return score

    def remember_compose(self, edit) -> None:
        """Cache the confirmed real compose field for this session."""
        try:
            self._preferred_rid = tuple(edit.element_info.runtime_id)
        except Exception:
            pass

    # -- click geometry -------------------------------------------------------

    def control_click_point(self, control):
        """(client_x, client_y) for a control's center, computed from UIA
        rects so button and window coordinates come from the same source
        (DPI-consistent). Telegram Desktop is frameless: window origin
        ~ client origin. Returns None when geometry is unreadable."""
        try:
            window = self._window()
            wrect = window.rectangle()
            r = control.rectangle()
            return (int((r.left + r.right) / 2.0 - wrect.left),
                    int((r.top + r.bottom) / 2.0 - wrect.top))
        except Exception:
            return None

    def compose_click_point(self, compose_box):
        return self.control_click_point(compose_box)

    # -- post-landing audit ---------------------------------------------------

    @staticmethod
    def _value_length(edit) -> int:
        """Content LENGTH only (R10: never the content itself). ValuePattern
        first, then LegacyIAccessible value."""
        try:
            vp = edit.iface_value
            return len(vp.CurrentValue or "")
        except Exception:
            pass
        try:
            legacy = edit.legacy_properties()
            if isinstance(legacy, dict):
                if "Value" not in legacy:
                    trace.trace(f"legacy keys: {sorted(legacy.keys())}")
                return len(legacy.get("Value") or "")
        except Exception:
            pass
        return -1  # unreadable — distinct from "verifiably empty"

    def edit_audit(self):
        """Inspect every Edit control and return (text_edit, entries):
        text_edit is the wrapper whose value length is > 0 (the text
        demonstrably landed there), or None; entries are trace-ready
        strings with geometry + value lengths only."""
        try:
            window = self._window()
            edits = window.descendants(control_type="Edit")
        except Exception:
            return None, []
        text_edit = None
        entries = []
        for i, edit in enumerate(edits):
            length = self._value_length(edit)
            try:
                rid = edit.element_info.runtime_id
            except Exception:
                rid = ()
            try:
                r = edit.rectangle()
                geo = f"({r.left},{r.top}) {r.width()}x{r.height()}"
            except Exception:
                geo = "rect unreadable"
            entries.append((edit, f"edit[{i}] at {geo} "
                            f"value_len={length} rid={rid}"))
            if length > 0 and text_edit is None:
                text_edit = edit
        return text_edit, entries

    # -- send button ------------------------------------------------------------

    def send_button_click(self, near_box=None):
        """Locate the Send button and return (name, client_x, client_y).

        Search order: the band around the text-holding Edit (`near_box`),
        then the window's bottom strip (the compose row lives there even
        when Edit geometry is unreliable). A button whose accessible name
        identifies a voice/mic control is deprioritized — the injector
        refuses to click those (with an empty compose that slot is the mic
        button). Unnamed candidates: rightmost wins (the compose row is
        [attach] [field] [emoji] [send|mic] — send is the rightmost).

        Final pass: any control named "*send*" near the compose.
        """
        hwnd = self.hwnd
        if not hwnd:
            return None
        try:
            window = self._window()
            wrect = window.rectangle()
            buttons = window.descendants(control_type="Button")
        except Exception:
            return None

        bands = []
        if near_box is not None:
            try:
                c = near_box.rectangle()
                bands.append(c)
            except Exception:
                pass
        # Window-bottom strip fallback: the compose row occupies the
        # bottom ~15% of the window.
        strip_top = max(int(wrect.top),
                        int(wrect.bottom - 0.15 * (wrect.bottom - wrect.top)))
        bands.append(_Band(wrect.left, strip_top, wrect.right, wrect.bottom))

        best = None  # (key, name, client_x, client_y)
        for button in buttons:
            try:
                r = button.rectangle()
                name = (button.element_info.name or "")
            except Exception:
                continue
            if not any(self._in_band(r, b) for b in bands):
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
                # unnamed: rightmost wins (emoji sits left of send)
                key = (1, -center_x, center_y)
            if best is None or key < best[0]:
                best = (key, name,
                        int(center_x - wrect.left),
                        int(center_y - wrect.top))
        if best is not None:
            return best[1], best[2], best[3]

        # Final pass: any control named "*send*" in the bands.
        try:
            for el in window.descendants():
                try:
                    name = (el.element_info.name or "")
                except Exception:
                    continue
                if "send" not in name.lower():
                    continue
                r = el.rectangle()
                if not any(self._in_band(r, b) for b in bands):
                    continue
                cx = int((r.left + r.right) / 2.0 - wrect.left)
                cy = int((r.top + r.bottom) / 2.0 - wrect.top)
                return name, cx, cy
        except Exception:
            pass
        return None

    @staticmethod
    def _in_band(r, band) -> bool:
        if r.right < band.left - 20 or r.left > band.right + 240:
            return False
        if r.bottom < band.top - 20 or r.top > band.bottom + 20:
            return False
        return True
