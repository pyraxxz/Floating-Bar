"""Locate the Telegram window, its compose box, and the Send button.

Window discovery: PROCESS IMAGE NAME first (telegram.exe / Telegram.exe
via EnumWindows) — the window title becomes the open chat's name and
usually contains no "Telegram", so title matching alone misses it. A
strict title fallback ("Telegram" / "Telegram Desktop") covers portable
installs that rename the exe.

UIA runtime IDs are session-scoped hints, never permanent identities. The
cache is invalidated when Telegram's top-level HWND/PID scope changes, and
remembered compose geometry is revalidated before use.
"""

import pywinauto
from pywinauto.findwindows import ElementNotFoundError

import config
from . import trace
from . import winapi
from .transaction import TargetScope


class _Band:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class TelegramNotFound(Exception):
    """Telegram Desktop (or its compose box) is not reachable."""


class TelegramTarget:
    """Cached Telegram window handle + compose-box finder."""

    def __init__(self):
        self._hwnd = None
        self._pid = None
        self._preferred_rid = None
        self._preferred_scope = None

    @property
    def hwnd(self) -> int:
        """A currently-valid Telegram top-level hwnd, or 0."""
        if self._hwnd and winapi.user32.IsWindow(self._hwnd):
            return self._hwnd
        self.refresh()
        return self._hwnd or 0

    def is_available(self) -> bool:
        return self.hwnd != 0

    def scope(self) -> TargetScope:
        """Return the currently discovered immutable `(hwnd, pid)` scope."""
        hwnd = self.hwnd
        if not hwnd:
            return TargetScope(0, 0)
        pid = self._pid or winapi.get_window_pid(hwnd)
        return TargetScope(hwnd, pid)

    def scope_matches(self, hwnd: int, pid: int = 0) -> bool:
        """True only when the same Telegram top-level window/process is current."""
        current_hwnd, current_pid = self.scope()
        expected_pid = pid or self._pid or 0
        return bool(
            hwnd and current_hwnd == hwnd and expected_pid and
            current_pid == expected_pid
        )

    def refresh(self, preferred_hwnd: int = 0) -> None:
        """Re-scan Telegram windows, optionally preferring a known foreground HWND."""
        previous_scope = (self._hwnd, self._pid)
        self._hwnd = None
        self._pid = None
        matches = winapi.find_windows(
            config.PROCESS_NAME_RE,
            title_re=config.TITLE_FALLBACK_RE,
        )

        chosen = None
        if preferred_hwnd:
            for match in matches:
                if match[0] == preferred_hwnd:
                    chosen = match
                    trace.trace(
                        f"telegram target: preferring foreground window hwnd={preferred_hwnd}"
                    )
                    break
        if chosen is None and matches:
            chosen = matches[0]

        if chosen is not None:
            self._hwnd, self._pid = chosen[0], chosen[1]

        current_scope = (self._hwnd, self._pid)
        if self._preferred_scope is not None and current_scope != previous_scope:
            trace.trace(
                "compose cache: Telegram window scope changed; "
                "discarding remembered runtime id"
            )
            self._preferred_rid = None
            self._preferred_scope = None

    def select_for_send(self, preferred_hwnd: int = 0) -> int:
        """Select a Telegram window for a send, preferring a known foreground HWND."""
        self.refresh(preferred_hwnd=preferred_hwnd)
        return self.hwnd

    def _window(self):
        hwnd = self.hwnd
        if not hwnd:
            raise TelegramNotFound("Telegram Desktop doesn't seem to be running.")
        app = pywinauto.Application(backend="uia").connect(handle=hwnd)
        return app.window(handle=hwnd).wrapper_object()

    def compose_box(self):
        try:
            window = self._window()
            edits = window.descendants(control_type="Edit")
        except (ElementNotFoundError, Exception) as e:
            self._hwnd = None
            self._pid = None
            raise TelegramNotFound(
                f"Could not read Telegram's window tree: {e}"
            ) from e

        if not edits:
            raise TelegramNotFound("No editable control found — is a chat actually open?")

        scope = (self._hwnd, self._pid)
        if self._preferred_rid is not None and self._preferred_scope == scope:
            for edit in edits:
                try:
                    if tuple(edit.element_info.runtime_id) != tuple(self._preferred_rid):
                        continue
                    if self._remembered_compose_is_valid(edit, window):
                        trace.trace("compose: using validated remembered inner field")
                        return edit
                    trace.trace(
                        "compose: remembered field failed validation; discarding cache"
                    )
                except Exception:
                    continue
            self._preferred_rid = None
            self._preferred_scope = None
        elif self._preferred_rid is not None:
            self._preferred_rid = None
            self._preferred_scope = None

        for i, edit in enumerate(edits):
            try:
                r = edit.rectangle()
                trace.trace(
                    f"edit[{i}] rect=({r.left},{r.top})-"
                    f"({r.right},{r.bottom}) {r.width()}x{r.height()}"
                )
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
            trace.trace(f"compose chosen: ({r.left},{r.top})-({r.right},{r.bottom})")
        except Exception:
            pass
        return best

    @classmethod
    def _remembered_compose_is_valid(cls, edit, window) -> bool:
        try:
            rect = edit.rectangle()
            if rect.width() <= 20 or rect.height() <= 5:
                return False
            win_rect = window.rectangle()
            win_h = float(win_rect.bottom - win_rect.top)
            if win_h <= 0:
                return False
            if rect.top < win_rect.top + (0.55 * win_h):
                return False
        except Exception:
            return False
        try:
            if edit.iface_value.CurrentIsReadOnly:
                return False
        except Exception:
            pass
        return True

    @staticmethod
    def _score_compose_candidate(edit, window):
        try:
            rect = edit.rectangle()
            area = float(rect.width()) * float(rect.height())
            top = float(rect.top)
        except Exception:
            return -1.0
        if area <= 0:
            return -1.0
        score = area
        try:
            win_rect = window.rectangle()
            win_h = float(win_rect.bottom - win_rect.top)
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
            pass
        return score

    def remember_compose(self, edit) -> None:
        try:
            self._preferred_rid = tuple(edit.element_info.runtime_id)
            self._preferred_scope = (self._hwnd, self._pid)
        except Exception:
            self._preferred_rid = None
            self._preferred_scope = None

    def control_click_point(self, control):
        try:
            window = self._window()
            wrect = window.rectangle()
            r = control.rectangle()
            return (
                int((r.left + r.right) / 2.0 - wrect.left),
                int((r.top + r.bottom) / 2.0 - wrect.top),
            )
        except Exception:
            return None

    def compose_click_point(self, compose_box):
        return self.control_click_point(compose_box)

    @staticmethod
    def _value_length(edit) -> int:
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
        return -1

    def edit_audit(self):
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
            entries.append((edit, f"edit[{i}] at {geo} value_len={length} rid={rid}"))
            if length > 0 and text_edit is None:
                text_edit = edit
        return text_edit, entries

    @staticmethod
    def _button_evidence_score(button, rect, name, compose_rect, window_rect) -> float:
        """Score a button using semantic, pattern, and compose-row evidence."""
        lname = (name or "").strip().lower()
        if any(term in lname for term in ("voice", "record", "mic", "audio")):
            return -1.0

        score = 0.0
        if "send" in lname:
            score += 100.0

        try:
            automation_id = (button.element_info.automation_id or "").strip().lower()
        except Exception:
            automation_id = ""
        if "send" in automation_id:
            score += 30.0

        try:
            button.iface_invoke
            score += 15.0
        except Exception:
            pass

        center_x = (rect.left + rect.right) / 2.0
        center_y = (rect.top + rect.bottom) / 2.0
        if compose_rect is not None:
            compose_center_y = (compose_rect.top + compose_rect.bottom) / 2.0
            compose_h = max(6, compose_rect.bottom - compose_rect.top)
            row_limit = max(18.0, 1.75 * compose_h)
            row_distance = abs(center_y - compose_center_y)
            if row_distance > row_limit:
                return -1.0
            score += 40.0 * max(0.0, 1.0 - (row_distance / row_limit))

            gap = center_x - compose_rect.right
            if gap >= 0:
                score += 25.0 / (1.0 + gap / 40.0)
            elif center_x >= compose_rect.left:
                score += 5.0
            else:
                score -= 35.0
        else:
            bottom_band = max(
                1.0,
                float(window_rect.bottom - window_rect.top),
            )
            vertical = (center_y - window_rect.top) / bottom_band
            score += max(0.0, min(1.0, vertical)) * 10.0

        width = max(1.0, rect.right - rect.left)
        height = max(1.0, rect.bottom - rect.top)
        if 12.0 <= width <= 120.0 and 12.0 <= height <= 120.0:
            score += 5.0
        return score

    @staticmethod
    def _button_has_explicit_send_semantics(button, name) -> bool:
        """True only when accessible text or automation metadata says "Send"."""
        lname = (name or "").strip().lower()
        if "send" in lname:
            return True
        try:
            automation_id = (button.element_info.automation_id or "").strip().lower()
        except Exception:
            automation_id = ""
        return "send" in automation_id

    def send_button_click(self, near_box=None):
        """Locate a safe Send-button candidate, with compose-row evidence."""
        hwnd = self.hwnd
        if not hwnd:
            return None
        try:
            window = self._window()
            wrect = window.rectangle()
            buttons = window.descendants(control_type="Button")
        except Exception:
            return None

        compose_rect = None
        if near_box is not None:
            try:
                compose_rect = near_box.rectangle()
            except Exception:
                pass

        bands = []
        if compose_rect is not None:
            h = max(1, compose_rect.bottom - compose_rect.top)
            bands.append(_Band(
                compose_rect.left - 20,
                compose_rect.top - max(18, int(1.75 * h)),
                wrect.right,
                compose_rect.bottom + max(18, int(1.75 * h)),
            ))
        strip_top = max(
            int(wrect.top),
            int(wrect.bottom - 0.15 * (wrect.bottom - wrect.top)),
        )
        bands.append(_Band(wrect.left, strip_top, wrect.right, wrect.bottom))

        candidates = []
        for button in buttons:
            try:
                r = button.rectangle()
                name = (button.element_info.name or "").strip()
            except Exception:
                continue
            if not any(self._in_band(r, b) for b in bands):
                continue
            try:
                if not button.is_enabled():
                    continue
            except Exception:
                pass

            score = self._button_evidence_score(
                button,
                r,
                name,
                compose_rect,
                wrect,
            )
            if score < 0:
                continue
            trace.trace(
                f"button candidate: score={score:.1f} name={name!r} "
                f"rect=({r.left},{r.top})-({r.right},{r.bottom})"
            )
            candidates.append((score, name, r, button))

        if not candidates:
            return None

        # A named control must identify itself as Send. This prevents unrelated
        # compose-row controls such as Attach/Emoji from being clicked merely
        # because they happen to score well geometrically. Unnamed icons may
        # still qualify through the evidence threshold below.
        candidates = [
            item for item in candidates
            if self._button_has_explicit_send_semantics(item[3], item[1])
            or (not item[1] and item[0] >= 35.0)
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda item: (-item[0], item[2].left, item[2].top))
        _, name, r, _button = candidates[0]
        return (
            name,
            int((r.left + r.right) / 2.0 - wrect.left),
            int((r.top + r.bottom) / 2.0 - wrect.top),
        )

    @staticmethod
    def _in_band(r, band) -> bool:
        if r.right < band.left - 20 or r.left > band.right + 40:
            return False
        if r.bottom < band.top - 20 or r.top > band.bottom + 20:
            return False
        return True
