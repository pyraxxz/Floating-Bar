"""Cascading injection — how text actually reaches Telegram.

Findings from the v0.1.3 trace log (a real user's Telegram Desktop build):

* The compose box DOES expose a ValuePattern — but it's broken: SetValue
  doesn't write (read-back mismatch), and CurrentValue always reports
  "" even while text is visibly in the field. A pattern that fails the
  write-verification must not be trusted for read-verification either —
  its "empty" reads caused every earlier version to declare fake success
  and stop after a single, dead posted Enter.
* Every posted ENTER keystroke variant (KEYDOWN/KEYUP, with/without
  WM_CHAR, both combos) fails to submit on this build. WM_CHAR text
  landing works; Enter as a key event does nothing.

So the submit is now: THE SEND BUTTON, clicked invisibly.

  PHASE 1 — land the text in the compose box
    A    UIA ValuePattern.SetValue — used only if the read-back verifies
    A2   posted WM_CHAR per UTF-16 code unit (empirically lands)

  PHASE 2 — submit, ALL invisible (no focus steal, no window raise)
    Verifiable state (trusted channel):
      post Enter combos, verify, then posted-click the Send button
    Unverifiable state (broken patterns — typical for this build):
      posted-click the Send button FIRST (compose verifiably-by-eye holds
      our text, so the compose button IS the send button), and only fall
      back to posted Enter combos when no button can be located.
      A button whose accessible name identifies it as a voice/mic control
      is never clicked — it means the text never landed.

  Posted clicks: WM_LBUTTONDOWN/WM_LBUTTONUP at the button's client
  coordinates — the background-window equivalent of AutoHotkey's
  ControlClick. No mouse movement, no activation, no window raise.

  AGGRESSIVE fallback (opt-in): config.ALLOW_FOCUS_STEAL = True re-enables
  the focus-stealing paths (dual-combo submit with real SendInput, then
  clipboard paste). Off by default — raising the window violates the
  product's core promise.

R10 note: all read-backs are compared against constants and reduced to
booleans — never stored, logged, or displayed. The trace log records stage
labels, channels and results only, never message content.
"""

import threading
import time

import config
from . import clipboard_guard
from . import trace
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
        # Whether the compose's ValuePattern can be trusted THIS send:
        # None = untested, True = verified, False = failed write-verify.
        self._vp_trusted = None

    # ------------------------------------------------------------------ API

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        text = (text or "").strip()
        if not text:
            return "skipped-empty"

        with self._lock:
            trace.section("send")
            trace.trace(f"text len={len(text)} (content never logged)")
            hwnd = self.target.hwnd
            if not hwnd:
                trace.trace("telegram window: NOT FOUND")
                raise TelegramNotFound(
                    "Telegram Desktop doesn't seem to be running."
                )
            trace.trace(f"telegram window: hwnd={hwnd} "
                        f"minimized={winapi.is_minimized(hwnd)}")
            box = self.target.compose_box()
            trace.trace(f"compose box: value_pattern="
                        f"{self._has_value_pattern(box)} text_pattern="
                        f"{self._has_text_pattern(box)}")
            primary_ctrl = config.ENTER_SEND_MODE == "ctrl+enter"
            self._vp_trusted = None

            # ---------------- PHASE 1: land the text ----------------
            landed = self._land_text(box, hwnd, text)
            trace.trace(f"phase 1 land text: {landed or 'FAILED'}")
            if not landed:
                trace.trace("phase 1 failed to land text at all")
                if not config.ALLOW_FOCUS_STEAL:
                    raise InjectionFailed(
                        "Text never reached Telegram's compose box, and the "
                        "clipboard fallback is disabled "
                        "(ALLOW_FOCUS_STEAL=False)."
                    )
                if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                    return "B-clipboard-paste"
                raise InjectionFailed(
                    "Every injection strategy failed — is a chat open?"
                )

            # ---------------- PHASE 2: submit (invisible) ----------------
            result = self._submit_invisible(box, hwnd, primary_ctrl)
            if result:
                trace.trace(f"submitted via: {result}")
                return result

            # ---------------- AGGRESSIVE fallback (opt-in) ----------------
            if not config.ALLOW_FOCUS_STEAL:
                trace.trace("invisible submit did not verify; "
                            "focus-steal disabled — stopping")
                raise InjectionFailed(
                    "Message sits in Telegram's compose box but could not "
                    "be submitted invisibly on this build. Set "
                    "ALLOW_FOCUS_STEAL = True in config.py to enable the "
                    "aggressive fallback (briefly raises Telegram), and "
                    "share trace.log so the cascade can be tuned."
                )
            if self._submit_focus_steal(box, hwnd, primary_ctrl, restore_hwnd):
                return "A-focus-enter"
            if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                return "B-clipboard-paste"
            trace.trace("cascade exhausted: all strategies failed")
            raise InjectionFailed(
                "Text reached the compose box but never submitted — "
                "check which chat is open and Telegram's Enter settings."
            )

    # -------------------------------------------------- Phase 1 strategies

    def _land_text(self, box, hwnd: int, text: str):
        """A (verified ValuePattern) then A2 (posted WM_CHAR)."""
        if self._try_set_text_value_pattern(box, text):
            return "A"
        try:
            winapi.post_text(hwnd, text)  # no focus steal; empirically lands
            return "A2"
        except Exception as e:
            trace.trace(f"WM_CHAR post failed: {e}")
            return None

    def _try_set_text_value_pattern(self, box, text: str) -> bool:
        try:
            vp = box.iface_value  # raises when the pattern is unsupported
        except Exception:
            trace.trace("valuepattern: unsupported by compose box")
            return False
        try:
            vp.SetValue(text)
        except Exception as e:
            trace.trace(f"valuepattern SetValue failed: {e}")
            return False
        try:
            ok = vp.CurrentValue == text
            self._vp_trusted = ok
            trace.trace(f"valuepattern SetValue verified: {ok}"
                        + ("" if ok else " — pattern UNTRUSTED this send"))
            return ok
        except Exception:
            self._vp_trusted = True  # can't verify the write — trust reads
            trace.trace("valuepattern SetValue: unverifiable, trusting")
            return True

    # ---------------------------------------------------- Phase 2: submit

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool):
        """The ONLY submit path by default. All posted messages — no focus
        change, no window raise, no real mouse movement."""
        state = self._compose_state(box)
        trace.trace(f"submit: state={state} "
                    f"(vp_trusted={self._vp_trusted})")

        if state == "unknown":
            return self._submit_unverified(box, hwnd, primary_ctrl)

        if state == "empty":
            # A trusted channel says the compose is empty even though we
            # just "landed" text — it went nowhere. Clicking the compose
            # button now would hit the MIC (voice recording); posting Enter
            # would send nothing (or a stale draft). Fail honestly.
            trace.trace("submit: text never landed (trusted empty)")
            raise InjectionFailed(
                "Text never reached Telegram's compose box."
            )

        # Trusted "text": posted Enter combos, verified, then the click.
        winapi.post_enter(hwnd, ctrl=primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        state = self._compose_state(box)
        trace.trace(f"posted combo 1: state={state}")
        if state == "empty":
            return "A-posted-enter"
        winapi.post_enter(hwnd, ctrl=not primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        state = self._compose_state(box)
        trace.trace(f"posted combo 2: state={state}")
        if state == "empty":
            return "A-posted-enter"
        # Still verifiably holding text — invisible button click.
        if self._posted_click_send_button(box, hwnd):
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            state = self._compose_state(box)
            trace.trace(f"posted click: state={state}")
            if state == "empty":
                return "posted-click"
        return None  # verified failure — caller escalates

    def _submit_unverified(self, box, hwnd: int, primary_ctrl: bool):
        """Unverifiable build (broken/unexposed patterns). Empirically the
        text HAS landed (the user sees it), so the compose-area button IS
        the send button: click it FIRST — Enter posts would, if they
        worked, empty the compose and turn that button into the mic."""
        if winapi.is_minimized(hwnd):
            trace.trace("telegram is minimized — posted click skipped "
                        "(client coords are meaningless while minimized)")
        else:
            info = self.target.send_button_click(box)
            if info is None:
                trace.trace("send button: no candidate found near compose")
            else:
                name, cx, cy = info
                lname = name.lower()
                if any(k in lname for k in
                       ("voice", "record", "mic", "audio")):
                    trace.trace(f"button is the mic ({name!r}) — refusing")
                    raise InjectionFailed(
                        "Telegram shows the voice button — the text did "
                        "not land in the compose box."
                    )
                trace.trace(f"posted click at ({cx},{cy}) "
                            f"name={name!r}")
                winapi.post_click(hwnd, cx, cy)
                return "posted-click (unverified)"

        # No button to click — last resort: post both Enter combos.
        trace.trace("falling back to posted enter combos")
        winapi.post_enter(hwnd, ctrl=primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        winapi.post_enter(hwnd, ctrl=not primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        return "posted-enter (unverified)"

    def _posted_click_send_button(self, box, hwnd: int) -> bool:
        """Verified-text path: the compose button is definitely Send —
        posted click, safe to use unconditionally here."""
        if winapi.is_minimized(hwnd):
            return False
        info = self.target.send_button_click(box)
        if info is None:
            trace.trace("send button: no candidate found near compose")
            return False
        name, cx, cy = info
        trace.trace(f"posted click at ({cx},{cy}) name={name!r}")
        winapi.post_click(hwnd, cx, cy)
        return True

    # -------------------------------------------- aggressive focus-steal

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """Opt-in only (ALLOW_FOCUS_STEAL): raise Telegram, dual-combo
        submit with real SendInput keystrokes, then the posted click."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            winapi.ensure_restored(hwnd)
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
            box.set_focus()
            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._compose_state(box) == "empty":
                return True
            box.type_keys(_combo(not primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            state = self._compose_state(box)
            trace.trace(f"focus-steal combos: state={state}")
            if state == "empty":
                return True
            if state == "text":
                if self._posted_click_send_button(box, hwnd):
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._compose_state(box) == "empty"
            return False
        except Exception as e:
            trace.trace(f"focus-steal submit failed: {e}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """Opt-in only: focus steal + Ctrl+A/Del clear + clipboard paste +
        dual-combo + posted click."""
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
                trace.trace(f"B: pasted, state={self._compose_state(box)}")

                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._compose_state(box) == "empty":
                    return True
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                state = self._compose_state(box)
                trace.trace(f"B combos: state={state}")
                if state == "empty":
                    return True
                if state == "text" and self._posted_click_send_button(box, hwnd):
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._compose_state(box) == "empty"
                return False
        except Exception as e:
            trace.trace(f"B failed: {e}")
            return False
        finally:
            # <- user's clipboard restored (all formats) at context exit
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # -------------------------------------------------------- verification

    @staticmethod
    def _has_value_pattern(box) -> bool:
        try:
            box.iface_value  # noqa: B018
            return True
        except Exception:
            return False

    @staticmethod
    def _has_text_pattern(box) -> bool:
        try:
            box.iface_text  # noqa: B018
            return True
        except Exception:
            return False

    def _compose_state(self, box) -> str:
        """'empty' | 'text' | 'unknown'.

        Channel order: ValuePattern (only when it passed the
        write-verification this send — the v0.1.3 trace showed a build
        whose pattern always reads "" while the field visibly holds text;
        an untrusted pattern's reads are lies), then TextPattern, then
        LegacyIAccessible value. R10: the content read here is reduced to
        a boolean — never stored, logged, or displayed."""
        if self._vp_trusted:
            try:
                vp = box.iface_value
                state = "text" if (vp.CurrentValue or "").strip() else "empty"
                trace.trace(f"state via valuepattern: {state}")
                return state
            except Exception:
                pass
        try:
            tp = box.iface_text
            value = tp.DocumentRange.GetText(-1)
            if isinstance(value, tuple):  # some comtypes marshaling
                value = value[0] if value else ""
            state = "text" if (value or "").strip() else "empty"
            trace.trace(f"state via textpattern: {state}")
            return state
        except Exception:
            pass
        try:
            legacy = box.legacy_properties()
            value = legacy.get("Value", "") if isinstance(legacy, dict) else ""
            state = "text" if (value or "").strip() else "empty"
            trace.trace(f"state via legacy: {state}")
            return state
        except Exception:
            pass
        trace.trace("state: unknown (no usable channel)")
        return "unknown"
