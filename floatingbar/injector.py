"""Cascading injection — how text actually reaches Telegram.

Findings from real trace logs (v0.1.3 + v0.1.4, a real Telegram build):

* The compose's ValuePattern is broken — SetValue no-ops and reads stay
  "" even while text is visibly in the field. Its reads must never be
  trusted after a failed write-verification.
* The LegacyIAccessible channel also reported "empty" right after the
  text visibly landed — so read channels on this build either lag or
  describe a different control entirely.
* ALL posted Enter keystroke variants fail to submit on this build.

v0.1.5 therefore stops trusting reads it cannot prove, and drives the
whole flow through the mouse channel:

  PHASE 0 — click the compose box (posted click at its center) so Qt's
  keyboard focus is on the real message field before any text is posted.

  PHASE 1 — land the text: verified ValuePattern.SetValue, else posted
  WM_CHAR per UTF-16 code unit.

  PHASE 1.5 — AUDIT every Edit control (value LENGTHS only — R10:
  never content). Three outcomes:
    * text found in our compose  -> landing confirmed; reads work here
    * text found in ANOTHER edit -> the compose click didn't take
      (focus was elsewhere, e.g. the search field); retry the click +
      text post once, then fail honestly rather than risk the mic button
    * text found nowhere readable -> "unknown": reads are stale on this
      build, but the compose click + WM_CHAR empirically work — proceed

  PHASE 2 — submit, invisible only (no focus steal, no window raise):
    * posted click on the Send button (band around the text-holding
      Edit, window-bottom strip fallback; a voice/mic-named button is
      NEVER clicked — with an empty compose that slot is the mic button)
    * if no button can be located: posted Enter combos as last resort
    * when the audit channel works, the submit is VERIFIED (re-audit:
      text gone = sent); otherwise optimistic.

R10 note: all read-backs are compared against constants and reduced to
lengths and booleans — never stored, logged, or displayed.
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
    return "^{ENTER}" if ctrl_enter else "{ENTER}"


class TelegramInjector:
    def __init__(self, target: TelegramTarget = None):
        self.target = target or TelegramTarget()
        self._lock = threading.Lock()
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
            minimized = winapi.is_minimized(hwnd)
            trace.trace(f"telegram window: hwnd={hwnd} "
                        f"minimized={minimized}")
            box = self.target.compose_box()
            primary_ctrl = config.ENTER_SEND_MODE == "ctrl+enter"
            self._vp_trusted = None

            # ---------------- PHASE 0: focus the compose ----------------
            if not minimized:
                point = self.target.compose_click_point(box)
                if point:
                    trace.trace(f"compose click at {point}")
                    winapi.post_click(hwnd, point[0], point[1])
                    time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
                else:
                    trace.trace("compose click point: unreadable")

            # ---------------- PHASE 1: land the text ----------------
            landed = self._land_text(box, hwnd, text)
            trace.trace(f"phase 1 land text: {landed or 'FAILED'}")
            if not landed:
                if not config.ALLOW_FOCUS_STEAL:
                    raise InjectionFailed(
                        "Text never reached Telegram's compose box, and "
                        "the clipboard fallback is disabled "
                        "(ALLOW_FOCUS_STEAL=False)."
                    )
                if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                    return "B-clipboard-paste"
                raise InjectionFailed(
                    "Every injection strategy failed — is a chat open?"
                )

            # ---------------- PHASE 1.5: audit where it landed ---------
            time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
            landing = self._audit_landing(box)
            if landing == "elsewhere":
                # The compose click didn't take — Qt focus was on another
                # Edit (e.g. the search field). One retry: click + re-post.
                trace.trace("landing elsewhere — retrying compose click "
                            "+ text post")
                if not minimized:
                    point = self.target.compose_click_point(box)
                    if point:
                        winapi.post_click(hwnd, point[0], point[1])
                        time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
                try:
                    winapi.post_text(hwnd, text)
                except Exception:
                    pass
                time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
                landing = self._audit_landing(box)
            if landing == "elsewhere":
                trace.trace("text still lands outside the compose — "
                            "refusing to touch the (mic) button")
                raise InjectionFailed(
                    "Telegram's message field could not be focused — "
                    "click once into the chat's message field, then try "
                    "again."
                )

            # ---------------- PHASE 2: submit (invisible) ----------------
            result = self._submit_invisible(box, hwnd, primary_ctrl,
                                            landing)
            if result:
                trace.trace(f"submitted via: {result}")
                return result

            # ---------------- AGGRESSIVE fallback (opt-in) ----------------
            if not config.ALLOW_FOCUS_STEAL:
                raise InjectionFailed(
                    "Message sits in Telegram's compose box but could not "
                    "be submitted invisibly on this build. Set "
                    "ALLOW_FOCUS_STEAL = True in config.py to enable the "
                    "aggressive fallback (briefly raises Telegram), and "
                    "share trace.log so the cascade can be tuned."
                )
            if self._submit_focus_steal(box, hwnd, primary_ctrl,
                                        restore_hwnd):
                return "A-focus-enter"
            if self._strategy_b(box, text, primary_ctrl, restore_hwnd):
                return "B-clipboard-paste"
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
            self._vp_trusted = True
            trace.trace("valuepattern SetValue: unverifiable, trusting")
            return True

    # -------------------------------------------------- Phase 1.5: audit

    def _audit_landing(self, box) -> str:
        """'compose' | 'elsewhere' | 'unknown'.

        R10: value LENGTHS only — content is never read into Python
        beyond len(), never stored, logged, or displayed."""
        try:
            text_edit, entries = self.target.edit_audit()
        except Exception as e:
            trace.trace(f"audit failed: {e}")
            return "unknown"
        for _, line in entries:
            trace.trace(f"audit: {line}")
        try:
            compose_rid = box.element_info.runtime_id
        except Exception:
            compose_rid = None
        if text_edit is None:
            trace.trace("audit: no Edit reports text (stale reads or "
                        "unreadable) — treating as unknown")
            return "unknown"
        try:
            text_rid = text_edit.element_info.runtime_id
        except Exception:
            text_rid = None
        if compose_rid is not None and text_rid is not None \
                and tuple(compose_rid) == tuple(text_rid):
            trace.trace("audit: text is in our compose — LANDING CONFIRMED")
            return "compose"
        trace.trace("audit: text landed in a DIFFERENT Edit than our "
                    "compose selection")
        return "elsewhere"

    # ---------------------------------------------------- Phase 2: submit

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool,
                          landing: str):
        """Posted click on the Send button; posted Enter combos only when
        no button can be located. All invisible."""
        info = None
        if not winapi.is_minimized(hwnd):
            info = self.target.send_button_click(near_box=box)
        if info is None:
            trace.trace("send button: no candidate — posting enter combos")
            winapi.post_enter(hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            winapi.post_enter(hwnd, ctrl=not primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            if landing == "compose":
                if self._audit_landing(box) in ("compose", "elsewhere"):
                    # Reads worked before and the text is still there —
                    # the Enter posts did not submit. Honest failure.
                    return None
            return "posted-enter (unverified)"

        name, cx, cy = info
        lname = name.lower()
        if any(k in lname for k in ("voice", "record", "mic", "audio")):
            if landing == "compose":
                # Compose verifiably holds text but the best button is the
                # mic — button identification failed. Fall to Enter posts.
                trace.trace("button scan returned the mic despite text in "
                            "compose — posting enter combos instead")
                winapi.post_enter(hwnd, ctrl=primary_ctrl)
                time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
                winapi.post_enter(hwnd, ctrl=not primary_ctrl)
                time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
                return None if self._audit_landing(box) in (
                    "compose", "elsewhere") else "posted-enter (unverified)"
            # Without landing confirmation, the mic means the compose is
            # empty — never click it.
            trace.trace("button is the mic and landing unconfirmed — "
                        "refusing to click")
            raise InjectionFailed(
                "Telegram shows the voice button — the text did not land "
                "in the compose box."
            )

        trace.trace(f"posted click on send button at ({cx},{cy}) "
                    f"name={name!r}")
        winapi.post_click(hwnd, cx, cy)
        time.sleep(config.PASTE_SETTLE_MS / 1000.0)

        if landing == "compose":
            if self._audit_landing(box) in ("compose", "elsewhere"):
                # Text still there — click didn't submit; try Enter posts
                # while the text verifiably remains (mic cannot appear).
                trace.trace("click did not submit — posting enter combos")
                winapi.post_enter(hwnd, ctrl=primary_ctrl)
                time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
                winapi.post_enter(hwnd, ctrl=not primary_ctrl)
                time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
                if self._audit_landing(box) in ("compose", "elsewhere"):
                    return None
                return "posted-click"
            trace.trace("audit: text gone after click — VERIFIED SENT")
            return "posted-click (verified)"
        return "posted-click (unverified)"

    # -------------------------------------------- aggressive focus-steal

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """Opt-in only (ALLOW_FOCUS_STEAL)."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            winapi.ensure_restored(hwnd)
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
            box.set_focus()
            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._audit_landing(box) != "compose":
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._audit_landing(box) != "compose":
                info = self.target.send_button_click(near_box=box)
                if info and not any(k in info[0].lower() for k in
                                    ("voice", "record", "mic", "audio")):
                    winapi.post_click(hwnd, info[1], info[2])
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._audit_landing(box) != "compose"
                return False
            return True
        except Exception as e:
            trace.trace(f"focus-steal submit failed: {e}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """Opt-in only: focus steal + Ctrl+A/Del clear + clipboard paste."""
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

                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._audit_landing(box) != "compose":
                    box.type_keys(_combo(not primary_ctrl), pause=0.02)
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._audit_landing(box) != "compose":
                    info = self.target.send_button_click(near_box=box)
                    if info and not any(k in info[0].lower() for k in
                                        ("voice", "record", "mic", "audio")):
                        winapi.post_click(hwnd, info[1], info[2])
                        time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                        return self._audit_landing(box) != "compose"
                    return False
                return True
        except Exception as e:
            trace.trace(f"B failed: {e}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)
