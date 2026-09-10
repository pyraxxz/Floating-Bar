"""Cascading injection — how text actually reaches Telegram.

Two independent problems:

  PHASE 1 — land the text in the compose box
    A    UIA ValuePattern.SetValue, verified by read-back (no focus steal)
    A2   posted WM_CHAR per UTF-16 code unit (no focus steal, empirically
         lands; unverifiable when no pattern is exposed)

  PHASE 2 — submit. Telegram is a Qt app: posted Enter keystrokes are
  frequently ignored, and the "Enter = newline / Ctrl+Enter = send"
  setting makes a plain Enter a no-op. So the submit is a chain of
  increasingly physical attempts, each traced:

    2a  posted Enter key triple (KEYDOWN/CHAR/KEYUP) — trusted only when
        verifiable
    2b  focus-steal: press the configured combo, then the ALTERNATE combo
        (pressing both is safe: if the first sent the message, the second
        lands on an empty compose and Telegram does nothing) — works
        under either Telegram Enter setting
    2c  Send-button fallback — verified compose still holds text:
        UIA InvokePattern, then a REAL mouse click at the button's
        center (pywinauto click_input). A physical click cannot be
        ignored the way posted keystrokes can. Only attempted when the
        compose verifiably holds text, or the button's accessible name
        contains "send" — with an empty compose that button is the mic
        button, and clicking it would start a voice recording.
    2d  full fallback: focus steal + Ctrl+A/Del clear + clipboard paste
        + dual-combo + button fallback. Clipboard preserved in every
        format; original foreground window restored after.

Verification uses ValuePattern when the compose exposes it, falling back
to TextPattern, and reports "unknown" when neither exists.

R10 note: all read-backs are compared against constants and reduced to
booleans — never stored, logged, or displayed. The trace log records
stage labels and results only, never message content.
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
            trace.trace(f"telegram window: hwnd={hwnd}")
            box = self.target.compose_box()
            trace.trace(f"compose box: {self._compose_state(box)} state, "
                        f"patterns: value={self._has_value_pattern(box)} "
                        f"text={self._has_text_pattern(box)}")
            primary_ctrl = config.ENTER_SEND_MODE == "ctrl+enter"
            trace.trace(f"primary combo: "
                        f"{'ctrl+enter' if primary_ctrl else 'enter'}")

            # ---------------- PHASE 1: land the text ----------------
            landed = self._land_text(box, hwnd, text)
            trace.trace(f"phase 1 land text: "
                        f"{'valuepattern' if landed == 'A' else landed or 'FAILED'}")
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
                trace.trace("cascade exhausted: all strategies failed")
                raise InjectionFailed(
                    "Every injection strategy failed — is a chat open?"
                )

            # ---------------- PHASE 2: submit ----------------
            # 2a — posted Enter, no focus steal.
            result = self._submit_posted(hwnd, box, primary_ctrl)
            if result:
                trace.trace(f"submitted via: {result}")
                return result
            trace.trace("posted enter: no verified submit")

            # 2b/2c/2d — all involve raising Telegram to the foreground.
            # That violates the product's core promise (invisible sending),
            # so they only run when explicitly enabled in config.
            if not config.ALLOW_FOCUS_STEAL:
                trace.trace("focus-steal disabled (ALLOW_FOCUS_STEAL=False): "
                            "invisible submit only — done")
                # Unverifiable builds already returned an optimistic label
                # above; reaching here means verification FAILED while the
                # text is verifiably still in the compose.
                raise InjectionFailed(
                    "Message sits in Telegram's compose box but could not "
                    "be submitted invisibly on this build. "
                    "Set ALLOW_FOCUS_STEAL = True in config.py to enable "
                    "the aggressive fallback (briefly raises Telegram), "
                    "and share trace.log so the cascade can be tuned."
                )

            if self._submit_focus_steal(box, hwnd, primary_ctrl, restore_hwnd):
                return "A-focus-enter"
            trace.trace("focus-steal submit: no verified result")

            # 2d — full fallback.
            if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                return "B-clipboard-paste"

            trace.trace("cascade exhausted: all strategies failed")
            raise InjectionFailed(
                "Text reached the compose box but never submitted — "
                "check which chat is open and Telegram's Enter settings."
            )

    # -------------------------------------------------- Phase 1 strategies

    def _land_text(self, box, hwnd: int, text: str):
        """A (verified) then A2 (posted WM_CHAR). Returns 'A', 'A2' or None."""
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
            trace.trace(f"valuepattern SetValue verified: {ok}")
            return ok
        except Exception:
            trace.trace("valuepattern SetValue: unverifiable, trusting")
            return True

    # ---------------------------------------------------- Phase 2: submit

    def _submit_posted(self, hwnd: int, box, primary_ctrl: bool):
        """2a — posted Enter keypresses. The ONLY invisible submit path, so
        it runs on every build, verifiable or not.

        Unverifiable builds (no ValuePattern/TextPattern on the compose —
        typical for Qt): posting is invisible and safe, so we post the
        configured combo AND the alternate combo. Pressing both is safe
        because an Enter on an already-sent empty compose is a no-op — this
        covers both Telegram Enter settings without ever raising a window.
        (Cosmetic risk: on builds where the primary already sent, the
        alternate may leave a stray newline draft; acceptable vs not
        sending at all.)

        Verifiable builds get verified retries of the primary combo, then
        the alternate, and report None only on verified failure."""
        state = self._compose_state(box)
        post_hwnd = winapi.get_focused_hwnd(hwnd)
        trace.trace(f"posted submit: state={state} focus_hwnd={post_hwnd}")

        if state == "unknown":
            winapi.post_enter(post_hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            winapi.post_enter(post_hwnd, ctrl=not primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            trace.trace("posted submit: both combos posted "
                        "(invisible, unverifiable build)")
            return "A-posted-enter (unverified)"

        for _ in range(max(1, config.POSTED_ENTER_RETRIES + 1)):
            winapi.post_enter(post_hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            if self._compose_state(box) == "empty":
                return "A-posted-enter"
        # Primary combo failed — post the alternate (safe no-op if the
        # first actually sent and the verification is merely lagging).
        winapi.post_enter(post_hwnd, ctrl=not primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        if self._compose_state(box) == "empty":
            return "A-posted-enter"
        trace.trace("posted submit: compose verifiably still holds text")
        return None

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """2b/2c — brief focus steal, dual-combo submit, then the
        send-button fallback (invoke + physical click)."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            state0 = self._compose_state(box)
            winapi.ensure_restored(hwnd)
            raised = winapi.set_foreground_window(hwnd)
            trace.trace(f"focus steal: telegram raised={raised} "
                        f"prev_hwnd={prev}")
            if not raised:
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
            box.set_focus()

            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            state = self._compose_state(box)
            trace.trace(f"combo 1 ({'ctrl+enter' if primary_ctrl else 'enter'}): "
                        f"compose={state}")
            if state == "empty":
                return True

            # Configured combo didn't submit — press the alternate combo.
            # Safe: if the first sent, this lands on an empty compose.
            box.type_keys(_combo(not primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            state = self._compose_state(box)
            trace.trace(f"combo 2 ({'enter' if primary_ctrl else 'ctrl+enter'}): "
                        f"compose={state}")
            if state == "empty":
                return True

            # 2c — button fallback.
            if state == "text":
                # Compose verifiably still holds text -> button is Send.
                if self._send_button_fallback(box, verified_text=True):
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    state = self._compose_state(box)
                    trace.trace(f"button fallback: compose={state}")
                    return state == "empty"
            else:
                # Unverifiable build: only click a button that is
                # explicitly named as a send button.
                if self._send_button_fallback(box, verified_text=False):
                    return True
            return False
        except Exception as e:
            trace.trace(f"focus-steal submit failed: {e}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # ------------------------------------------------------- Strategy B

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """2d — full fallback: focus steal, deterministic compose clear,
        clipboard paste, dual-combo submit, button fallback."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            with clipboard_guard.preserved_clipboard(
                retries=config.CLIPBOARD_RETRIES,
                delay=config.CLIPBOARD_RETRY_DELAY_S,
            ):
                hwnd = self.target.hwnd or 0
                winapi.ensure_restored(hwnd)
                raised = winapi.set_foreground_window(hwnd)
                trace.trace(f"B: telegram raised={raised}")
                if not raised:
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
                trace.trace(f"B: pasted, compose={self._compose_state(box)}")

                # Dual-combo submit (same safety argument as 2b).
                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                state = self._compose_state(box)
                trace.trace(f"B combo 1: compose={state}")
                if state == "empty":
                    return True
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                state = self._compose_state(box)
                trace.trace(f"B combo 2: compose={state}")
                if state == "empty":
                    return True
                if state == "text":
                    if self._send_button_fallback(box, verified_text=True):
                        time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                        state = self._compose_state(box)
                        trace.trace(f"B button fallback: compose={state}")
                        return state == "empty"
                else:
                    # Unverifiable: name-gated button click only.
                    if self._send_button_fallback(box, verified_text=False):
                        return True
                return False
        except Exception as e:
            trace.trace(f"B failed: {e}")
            return False
        finally:
            # <- user's clipboard restored (all formats) at context exit
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    # -------------------------------------------------------- send button

    def _send_button_fallback(self, box, verified_text: bool) -> bool:
        """2c — invoke then physically click the Send button.

        Gate: with an EMPTY compose, Telegram's compose-area button is the
        mic button — clicking it starts a voice recording. So we click
        only when (a) the compose verifiably holds text, or (b) the
        button's accessible name explicitly identifies it as a send
        button (the mic button is named differently).
        """
        button = None
        name = ""
        try:
            button = self.target.find_send_button(box)
        except Exception as e:
            trace.trace(f"send button: finder failed: {e}")
        if button is None:
            trace.trace("send button: no candidate found near compose")
            return False
        try:
            name = (button.element_info.name or "")
        except Exception:
            name = ""
        named_send = "send" in name.lower()
        trace.trace(f"send button: name={name!r} named_send={named_send}")

        if not verified_text and not named_send:
            trace.trace("send button: refusing to click (cannot prove "
                        "compose holds text and button is not named send)")
            return False

        # 1) InvokePattern — cleanest, no mouse movement.
        try:
            button.iface_invoke.Invoke()
            trace.trace("send button: invoke() called")
            return True
        except Exception as e:
            trace.trace(f"send button: invoke unavailable ({type(e).__name__})")

        # 2) A REAL click at the button's center — cannot be ignored.
        try:
            button.click_input()
            trace.trace("send button: physically clicked")
            return True
        except Exception as e:
            trace.trace(f"send button: click failed: {e}")
            return False

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

    @staticmethod
    def _compose_state(box) -> str:
        """'empty' | 'text' | 'unknown'. R10: the compose content read here
        is reduced to a boolean — never stored, logged, or displayed."""
        # ValuePattern first — direct and cheap.
        try:
            vp = box.iface_value
            try:
                return "text" if (vp.CurrentValue or "").strip() else "empty"
            except Exception:
                pass
        except Exception:
            pass
        # TextPattern fallback — Qt line edits often expose this instead.
        try:
            tp = box.iface_text
            value = tp.DocumentRange.GetText(-1)
            if isinstance(value, tuple):  # some comtypes marshaling
                value = value[0] if value else ""
            return "text" if (value or "").strip() else "empty"
        except Exception:
            pass
        return "unknown"
