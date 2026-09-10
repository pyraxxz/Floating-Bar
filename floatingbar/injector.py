"""Cascading injection — how text actually reaches Telegram.

Redesigned after real-world testing on Telegram Desktop (Qt): landing the
text in the compose box is EASY (UIA ValuePattern or posted WM_CHAR both
work), but SUBMITTING is the hard half — Telegram frequently ignores
posted WM_KEYDOWN Enter keystrokes, and its "Enter = newline /
Ctrl+Enter = send" setting makes a plain Enter do nothing.

So the cascade is now two independent problems:

  PHASE 1 — land the text in the compose box
    A    UIA ValuePattern.SetValue, verified by read-back (no focus steal)
    A2   posted WM_CHAR per UTF-16 code unit (no focus steal, unverifiable)

  PHASE 2 — submit, least disruptive first
    2a   posted Enter keypress (works on some setups; verified if possible)
    2b   focus-steal submit: press the configured combo (config.
         ENTER_SEND_MODE), verify; if it didn't take, press the ALTERNATE
         combo. Pressing both is safe: if the first combo sent the message,
         the second lands on an empty compose and Telegram does nothing.
         This makes the app work no matter which Enter mode the user's
         Telegram is configured with.
    2c   (only when verifiable: compose still holds our text) invoke the
         Send button via UIA InvokePattern — never blind-invoked, because
         when the compose is empty that button is the mic button.
    2d   full fallback: focus-steal, Ctrl+A+Delete to clear the compose
         deterministically, clipboard paste, then the dual-combo submit.
         The user's clipboard is preserved across ALL formats and the
         original foreground window is restored afterwards.

R10 note: when a ValuePattern is available, compose content is read back
for verification ONLY — the value is compared against constants and is
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


def _combo(ctrl_enter: bool) -> str:
    """pywinauto type_keys sequence for the given send combo."""
    return "^{ENTER}" if ctrl_enter else "{ENTER}"


class TelegramInjector:
    def __init__(self, target: TelegramTarget = None):
        self.target = target or TelegramTarget()
        # Serialize sends: two concurrent focus-steal paths would fight
        # over the foreground window and double-paste.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        """Inject `text` into Telegram's open chat. Returns the strategy
        label that succeeded (diagnostics only — never the content).
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
            primary_ctrl = config.ENTER_SEND_MODE == "ctrl+enter"

            # ---------------- PHASE 1: land the text ----------------
            landed = self._land_text(box, hwnd, text)

            # ---------------- PHASE 2: submit ----------------
            # 2a — posted Enter (zero disruption). Try retries only when
            # we can actually verify the outcome; unverifiable = move on
            # to the deterministic focus-steal submit immediately.
            if not landed:
                # Nothing landed without a steal — go straight to the
                # full fallback (clear + paste + dual-combo submit).
                if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                    return "B-clipboard-paste"
                raise InjectionFailed(
                    "Every injection strategy failed — is a chat open?"
                )

            result = self._submit_posted(hwnd, box, primary_ctrl)
            if result:
                return result

            # 2b/2c — deterministic focus-steal submit (dual combo).
            if self._submit_focus_steal(box, hwnd, primary_ctrl, restore_hwnd):
                return "A-focus-enter"

            # 2d — full fallback.
            if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                return "B-clipboard-paste"

            raise InjectionFailed(
                "Text reached the compose box but never submitted — "
                "check which chat is open and Telegram's Enter settings."
            )

    # -------------------------------------------------- Phase 1 strategies

    def _land_text(self, box, hwnd: int, text: str) -> bool:
        """A (ValuePattern, verified) then A2 (posted WM_CHAR, unverifiable).
        Returns True if the text is in the compose (or very likely is)."""
        if self._try_set_text_value_pattern(box, text):
            return True
        try:
            winapi.post_text(hwnd, text)  # no focus steal; empirically lands
            return True
        except Exception:
            return False

    def _try_set_text_value_pattern(self, box, text: str) -> bool:
        try:
            vp = box.iface_value  # raises when the pattern is unsupported
        except Exception:
            return False
        try:
            vp.SetValue(text)
        except Exception:
            return False
        # R10: comparison against our own text only — never stored/logged.
        try:
            return vp.CurrentValue == text
        except Exception:
            return True  # can't verify — trust the SetValue

    # ---------------------------------------------------- Phase 2: submit

    def _submit_posted(self, hwnd: int, box, primary_ctrl: bool):
        """2a — posted Enter, no focus steal. Returns a label on verified
        success, None when unverifiable or not submitted."""
        vp = self._get_vp(box)
        if vp is None:
            return None  # can't verify a posted keystroke — don't gamble
        for _ in range(max(1, config.POSTED_ENTER_RETRIES + 1)):
            winapi.post_enter(hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            if self._is_empty(vp) is True:
                return "A-posted-enter"
        return None

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """2b/2c — brief focus steal, press the configured combo, verify,
        then press the alternate combo. Pressing both is safe: if the first
        combo sent the message, the second lands on an empty compose and
        Telegram does nothing with it."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            vp = self._get_vp(box)
            winapi.ensure_restored(hwnd)
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
            box.set_focus()

            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if vp is not None:
                if self._is_empty(vp) is True:
                    return True
                # Configured combo didn't submit — probably the user's
                # Telegram uses the other Enter mode. Press the alternate.
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._is_empty(vp) is True:
                    return True
                # 2c — compose verifiably still holds our text: the button
                # in the compose area is still the Send button. Invoke it.
                if self._invoke_send_button(box):
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._is_empty(vp) is True
                return False
            else:
                # Unverifiable: press both combos — covers both Telegram
                # Enter settings. If the first sent, the second is a no-op
                # on the empty compose.
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                return True
        except Exception:
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # ------------------------------------------------------- Strategy B

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """2d — full fallback: focus steal, deterministic compose clear
        (Ctrl+A, Del), clipboard paste, dual-combo submit. The user's
        clipboard is preserved in every format and the original foreground
        window is restored."""
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
                box.type_keys("^a", pause=0.01)
                box.type_keys("{DEL}", pause=0.01)
                clipboard_guard.set_text(
                    text,
                    retries=config.CLIPBOARD_RETRIES,
                    delay=config.CLIPBOARD_RETRY_DELAY_S,
                )
                box.type_keys("^v", pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)

                # Dual-combo submit (same safety argument as 2b).
                vp = self._get_vp(box)
                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if vp is not None:
                    if self._is_empty(vp) is True:
                        return True
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if vp is not None:
                    if self._is_empty(vp) is True:
                        return True
                    # Compose verifiably still holds the pasted text —
                    # invoke the Send button as the final move.
                    if self._invoke_send_button(box):
                        time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                        return self._is_empty(vp) is True
                    return False
                return True  # unverifiable — we did everything possible
        except Exception:
            return False
        finally:
            # <- user's clipboard restored (all formats) at context exit
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # -------------------------------------------------------- send button

    def _invoke_send_button(self, box) -> bool:
        """2c — invoke Telegram's Send button via UIA. ONLY called when the
        compose verifiably still holds our text: with an empty compose that
        button becomes the mic button, and invoking it would start a voice
        recording. Returns True if an InvokePattern call was made."""
        try:
            button = self.target.find_send_button(box)
            if button is None:
                return False
            button.iface_invoke.Invoke()
            return True
        except Exception:
            return False

    # -------------------------------------------------------- verification

    @staticmethod
    def _get_vp(box):
        """ValuePattern for the compose box, or None if unsupported."""
        try:
            return box.iface_value
        except Exception:
            return None

    @staticmethod
    def _is_empty(vp) -> bool:
        """True/False when verifiable; never called with vp=None.
        R10: comparison only — the value is never stored, logged, shown."""
        try:
            return not (vp.CurrentValue or "").strip()
        except Exception:
            return True  # can't verify — assume it worked
