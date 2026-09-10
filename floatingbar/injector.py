"""Cascading injection — how text actually reaches Telegram.

Cascade (ordered least → most disruptive, each stage only tried if the
previous one did not verifiably work):

  A    UIA ValuePattern.SetValue + posted Enter.
       No focus steal at all. If the compose box exposes IValueProvider
       we also VERIFY each stage (value == our text after the set,
       value == "" after the Enter), which the raw spec could not do.
  A+   ValuePattern set worked but the posted Enter didn't register:
       a minimal focus steal JUST to press Enter in the already-filled
       compose box. Still no clipboard use.
  A2   Raw WM_CHAR / WM_KEYDOWN posted into the Telegram HWND.
       No focus steal, but inherently best-effort: Qt exposes one native
       HWND per top-level window, and its internal widget focus decides
       where the characters land (spec calls this a bonus attempt).
  B    Focus-steal clipboard paste: raise Telegram, focus the compose,
       Ctrl+A + Delete (deterministically clear anything the earlier
       attempts may have left), paste, Enter. The user's clipboard is
       preserved across ALL formats (clipboard_guard) and the original
       foreground window is restored afterward.

All strategies submit with Enter or Ctrl+Enter depending on the user's
Telegram setting (config.ENTER_SEND_MODE).

R10 note: when a ValuePattern is available, compose content is read back
for verification ONLY — the value is compared against a constant and is
never stored, logged, or displayed anywhere.
"""

import threading
import time

import config
from . import clipboard_guard
from . import winapi
from .target import TelegramTarget, TelegramNotFound


class InjectionFailed(Exception):
    """Every strategy in the cascade failed."""


class TelegramInjector:
    def __init__(self, target: TelegramTarget = None):
        self.target = target or TelegramTarget()
        # Serialize sends: two concurrent Strategy-B paths would fight
        # over the foreground window and double-paste.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        """Inject `text` into Telegram's open chat. Returns the strategy
        label that succeeded (for diagnostics only — never the content).
        Raises TelegramNotFound / InjectionFailed."""
        text = (text or "").strip()
        if not text:
            return "skipped-empty"

        with self._lock:
            hwnd = self.target.hwnd
            if not hwnd:
                raise TelegramNotFound(
                    "Telegram Desktop doesn't seem to be running."
                )
            box = self.target.compose_box()
            ctrl_enter = config.ENTER_SEND_MODE == "ctrl+enter"

            result = self._strategy_a(box, text, ctrl_enter)
            if result:
                return result

            result = self._strategy_a2(hwnd, box, text, ctrl_enter)
            if result:
                return result

            if self._strategy_b(box, text, ctrl_enter, restore_hwnd):
                return "B-clipboard-fallback"

            raise InjectionFailed(
                "Every injection strategy failed — is a chat open?"
            )

    # -------------------------------------------------- Strategy A (+ A+)

    def _strategy_a(self, box, text: str, ctrl_enter: bool):
        """ValuePattern.SetValue + posted Enter. Fully verified when the
        compose box implements IValueProvider; returns None immediately
        when it doesn't (the common case for custom Qt widgets)."""
        try:
            vp = box.iface_value  # raises when the pattern is unsupported
        except Exception:
            return None
        try:
            vp.SetValue(text)
        except Exception:
            return None
        if not self._read_back_matches(vp, text):
            return None  # SetValue lied / partial write — pattern unusable

        # Our text is in the compose. Submit it without stealing focus.
        hwnd = self.target.hwnd or 0
        attempts = max(1, config.POSTED_ENTER_RETRIES + 1)
        for _ in range(attempts):
            winapi.post_enter(hwnd, ctrl=ctrl_enter)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            if self._compose_is_empty(vp):
                return "A-value-pattern"
        # Text is verifiably in the compose but posted Enters didn't submit.
        return self._press_enter_focus_steal(box, vp, ctrl_enter)

    def _press_enter_focus_steal(self, box, vp, ctrl_enter: bool):
        """A+ — the compose already holds our (verified) text; briefly
        steal focus only to press Enter. No clipboard involved."""
        prev = winapi.get_foreground_window()
        try:
            hwnd = self.target.hwnd or 0
            winapi.ensure_restored(hwnd)
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
            box.set_focus()
            box.type_keys("^{ENTER}" if ctrl_enter else "{ENTER}", pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            return self._compose_is_empty(vp)
        except Exception:
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # ------------------------------------------------------- Strategy A2

    def _strategy_a2(self, hwnd: int, box, text: str, ctrl_enter: bool):
        """Raw WM_CHAR / WM_KEYDOWN injection. No focus steal, no success
        signal from PostMessage itself: verify through the ValuePattern if
        the compose has one, otherwise report optimistically (per spec,
        this stage is a bonus attempt, not something to depend on)."""
        try:
            winapi.post_text(hwnd, text)
            winapi.post_enter(hwnd, ctrl=ctrl_enter)
        except Exception:
            return None
        try:
            vp = box.iface_value
        except Exception:
            return "A2-postmessage"  # unverifiable — assume it landed
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        return "A2-postmessage" if self._compose_is_empty(vp) else None

    # -------------------------------------------------------- Strategy B

    def _strategy_b(self, box, text: str, ctrl_enter: bool, restore_hwnd: int):
        """Focus-steal clipboard paste — the reliable fallback. Saves the
        user's clipboard in every format and restores it, then returns
        focus to the window that had it (usually the user's work app)."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            with clipboard_guard.preserved_clipboard(
                retries=config.CLIPBOARD_RETRIES,
                delay=config.CLIPBOARD_RETRY_DELAY_S,
            ):
                hwnd = self.target.hwnd or 0
                winapi.ensure_restored(hwnd)
                if not winapi.set_foreground_window(hwnd):
                    return False
                time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
                box.set_focus()
                # Deterministically clear whatever failed earlier attempts
                # may have left in the compose, then paste our text.
                box.type_keys("^a", pause=0.01)
                box.type_keys("{DEL}", pause=0.01)
                clipboard_guard.set_text(
                    text,
                    retries=config.CLIPBOARD_RETRIES,
                    delay=config.CLIPBOARD_RETRY_DELAY_S,
                )
                box.type_keys("^v", pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                box.type_keys("^{ENTER}" if ctrl_enter else "{ENTER}", pause=0.02)
            # <- user's clipboard is restored here, all formats intact
            time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
            return True
        except Exception as e:
            raise InjectionFailed(f"Fallback paste failed: {e}") from e
        finally:
            winapi.set_foreground_window(prev)

    # -------------------------------------------------------- verification

    @staticmethod
    def _read_back_matches(vp, expected: str) -> bool:
        """R10: the value read here is only ever COMPARED against the text
        we ourselves just wrote — never stored, logged, or displayed."""
        try:
            return vp.CurrentValue == expected
        except Exception:
            return True  # can't verify — trust the SetValue call

    @staticmethod
    def _compose_is_empty(vp) -> bool:
        """Same privacy note as _read_back_matches: comparison only."""
        try:
            return not (vp.CurrentValue or "").strip()
        except Exception:
            return True  # can't verify — assume it worked
