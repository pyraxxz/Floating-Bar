"""Cascading injection — how text actually reaches Telegram.

THE COMPLETE PICTURE (v0.1.5 trace log, real Telegram build):

Telegram's compose is TWO NESTED Edit controls, 1px apart: an outer
wrapper whose ValuePattern never writes and always reads "" — and the
INNER field, which actually holds the text and whose read channel works.
Every earlier version read the wrapper and saw "empty" while the text sat
in the inner field; v0.1.5's safety logic then saw "text in a different
control" and refused to click the Send button. The text lands perfectly;
the audit now proves it.

v0.1.6 flow (all invisible — no focus steal, no window raise):

  PHASE 1 — land the text: posted WM_CHAR per UTF-16 code unit. The old
  ValuePattern.SetValue path was removed in v0.1.7: Qt focuses the edit
  when an automation client writes its value, which raised Telegram's
  window on the first send of every session (and the write never worked
  on real builds anyway — the wrapper Edit's SetValue silently no-ops).

  PHASE 1.5 — AUDIT every Edit (value LENGTHS only — R10: never
  content). If the text is in a DIFFERENT Edit that geometrically
  overlaps our chosen one, it's the nested inner field: re-target the
  compose to it (and remember it for later sends) — that gives us a
  REAL verification channel. If the text landed in a non-overlapping
  Edit (e.g. the search field), retry the compose click + text post
  once, then fail honestly rather than ever risking the mic button.

  PHASE 2 — submit: posted click on the Send button (voice/mic-named
  buttons are never clicked), then VERIFY via the working channel —
  text gone = sent. If verification is impossible, the click is still
  safe (our text demonstrably sits in the compose) and the result is
  optimistic. If no button can be located, posted Enter combos are the
  last resort.

  GUARDS — minimized Telegram fails immediately and honestly (text
  cannot land while minimized; the v0.1.5 trace showed reads freeze
  too). After every send, if Telegram somehow ended up in the
  foreground (a posted click side effect), the user's previous
  foreground window is restored.

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


def _rects(a, b):
    """(intersection, area_a, area_b) of two pywinauto rects."""
    ix = max(0, min(a.right, b.right) - max(a.left, b.left))
    iy = max(0, min(a.bottom, b.bottom) - max(a.top, b.top))
    area_a = max(1, (a.right - a.left) * (a.bottom - a.top))
    area_b = max(1, (b.right - b.left) * (b.bottom - b.top))
    return ix * iy, area_a, area_b


def _nested(a, b, ratio: float = 0.5) -> bool:
    """True when two rects are the same visual field (nested/overlapping)."""
    try:
        inter, area_a, area_b = _rects(a, b)
        return (inter / min(area_a, area_b)) >= ratio
    except Exception:
        return False


class TelegramInjector:
    def __init__(self, target: TelegramTarget = None):
        self.target = target or TelegramTarget()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        # Preserve intentional leading/trailing whitespace. Whitespace-only
        # input is still treated as empty and skipped.
        text = text or ""
        if not text.strip():
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
            if winapi.is_minimized(hwnd):
                trace.trace("telegram is minimized — refusing honestly")
                raise InjectionFailed(
                    "Telegram is minimized — text can't reach it. Bring "
                    "it back to the background (behind your work is "
                    "fine, just not minimized) and try again."
                )
            prev_fg = restore_hwnd or winapi.get_foreground_window()
            trace.trace(f"telegram window: hwnd={hwnd} "
                        f"prev_fg={prev_fg}")
            box = self.target.compose_box()
            primary_ctrl = config.ENTER_SEND_MODE == "ctrl+enter"

            try:
                # ---------------- PHASE 1: land the text ----------------
                landed = self._land_text(box, hwnd, text)
                trace.trace(f"phase 1 land text: {landed or 'FAILED'}")
                if not landed:
                    raise InjectionFailed(
                        "Text never reached Telegram's compose box."
                    )

                # ---------------- PHASE 1.5: audit + re-target ----------
                landing, box = self._audit_and_retarget(box, hwnd, text)

                # ---------------- PHASE 2: submit (invisible) ----------
                if landing == "elsewhere":
                    raise InjectionFailed(
                        "Telegram's message field could not be focused — "
                        "click once into the chat's message field, then "
                        "try again."
                    )
                try:
                    return self._submit_invisible(box, hwnd, primary_ctrl,
                                                   landing)
                except InjectionFailed:
                    if not config.ALLOW_FOCUS_STEAL:
                        raise
                    # Opt-in aggressive fallback (briefly raises Telegram)
                    trace.trace("invisible submit failed — opt-in "
                                "focus-steal fallback engaged")
                    if self._submit_focus_steal(box, hwnd, primary_ctrl,
                                                 prev_fg):
                        return "A-focus-enter"
                    if self._strategy_b(box, text, primary_ctrl, prev_fg):
                        return "B-clipboard-paste"
                    raise
            except InjectionFailed:
                raise
            except Exception as e:
                trace.trace(f"send failed: {e}")
                raise InjectionFailed(f"Send failed: {e}")
            finally:
                # If a posted click side effect raised Telegram, put the
                # user's window back — invisibility is the product.
                self._restore_foreground(hwnd, prev_fg)

    # -------------------------------------------------- Phase 1 strategies

    def _land_text(self, box, hwnd: int, text: str):
        """Text lands via posted WM_CHAR per UTF-16 code unit — invisible
        and empirically reliable. No UIA writes: Qt focuses the edit when
        an automation client sets its value, raising Telegram's window
        (v0.1.6's first-send-only raise), and the write silently no-ops
        on real Telegram builds anyway."""
        try:
            winapi.post_text(hwnd, text)  # no focus steal; empirically lands
            return "A2"
        except Exception as e:
            trace.trace(f"WM_CHAR post failed: {e}")
            return None

    # -------------------------------------------------- Phase 1.5: audit

    def _audit_and_retarget(self, box, hwnd: int, text: str):
        """Audit where the text landed. Returns (landing, box) where box
        may have been re-targeted to the real inner field.

        R10: value LENGTHS only — content is never read beyond len()."""
        time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
        landing, real = self._audit(box)
        if real is None:
            return "unknown", box

        if self._same_field(real, box):
            # Nested inner field — the real compose. From now on reads
            # from it are trustworthy.
            trace.trace("audit: text is in the NESTED inner field — "
                        "re-targeting compose (reads now verifiable)")
            self.target.remember_compose(real)
            return "compose", real

        # Text in a non-overlapping Edit: focus was elsewhere (e.g. the
        # search field). One retry with a compose click, then honest fail.
        trace.trace("landing in a different field — retrying compose "
                    "click + text post")
        point = self.target.compose_click_point(box)
        if point:
            winapi.post_click(hwnd, point[0], point[1])
            time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
        try:
            winapi.post_text(hwnd, text)
        except Exception:
            pass
        time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
        landing, real = self._audit(box)
        if real is not None and self._same_field(real, box):
            self.target.remember_compose(real)
            return "compose", real
        return "elsewhere", box

    def _audit(self, box):
        """Returns (landing_label, text_edit). Landing: 'found' when some
        Edit holds text, 'none' when no Edit reports any text."""
        try:
            text_edit, entries = self.target.edit_audit()
        except Exception as e:
            trace.trace(f"audit failed: {e}")
            return "none", None
        for _, line in entries:
            trace.trace(f"audit: {line}")
        if text_edit is None:
            trace.trace("audit: no Edit reports text — reads stale or "
                        "unreadable, proceeding empirically")
            return "none", None
        return "found", text_edit

    @staticmethod
    def _same_field(a, b) -> bool:
        try:
            ra, rb = a.rectangle(), b.rectangle()
            return _nested(ra, rb)
        except Exception:
            return False

    # ---------------------------------------------------- Phase 2: submit

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool,
                          landing: str):
        """Posted click on the Send button; posted Enter combos only when
        no button can be located. All invisible."""
        verified = landing == "compose"
        if verified:
            # A working read channel: the compose verifiably holds text,
            # so the compose button IS the send button.
            length_before = self._value_length(box)
            trace.trace(f"submit: verified channel, "
                        f"compose value_len={length_before}")
            if length_before == 0:
                trace.trace("submit: verified channel says compose is "
                            "EMPTY — refusing to click (mic hazard)")
                raise InjectionFailed(
                    "The message text is not in Telegram's compose box."
                )

        info = self.target.send_button_click(near_box=box)
        if info is None:
            trace.trace("send button: no candidate — posting enter combos")
            winapi.post_enter(hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            winapi.post_enter(hwnd, ctrl=not primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            if verified and self._value_length(box) > 0:
                trace.trace("enter combos failed verification")
                raise InjectionFailed(
                    "Message sits in Telegram's compose box but could "
                    "not be submitted. Share trace.log so the cascade "
                    "can be tuned for this Telegram build."
                )
            return "posted-enter (unverified)"

        name, cx, cy = info
        if any(k in name.lower() for k in
               ("voice", "record", "mic", "audio")):
            trace.trace(f"button scan returned the mic ({name!r}) — "
                        "refusing to click")
            raise InjectionFailed(
                "Telegram's voice button is showing — the compose is "
                "empty, so the text did not land."
            )

        trace.trace(f"posted click on send button at ({cx},{cy}) "
                    f"name={name!r}")
        winapi.post_click(hwnd, cx, cy)
        time.sleep(config.PASTE_SETTLE_MS / 1000.0)

        if verified:
            length_after = self._value_length(box)
            trace.trace(f"submit verified: compose value_len={length_after}")
            if length_after == 0:
                return "posted-click (VERIFIED)"
            raise InjectionFailed(
                "The Send button was clicked but the message is still "
                "in the compose box. Share trace.log so the click "
                "coordinates can be tuned for this Telegram build."
            )
        return "posted-click (unverified)"

    @staticmethod
    def _value_length(box) -> int:
        try:
            vp = box.iface_value
            return len(vp.CurrentValue or "")
        except Exception:
            return -1

    # ------------------------------------------------------------ guards

    @staticmethod
    def _restore_foreground(telegram_hwnd: int, prev_fg: int) -> None:
        """If Telegram ended up in the foreground (posted clicks can
        activate Qt windows), put the user's window back."""
        try:
            current = winapi.get_foreground_window()
            if telegram_hwnd and current == telegram_hwnd \
                    and prev_fg and prev_fg != telegram_hwnd:
                winapi.set_foreground_window(prev_fg)
                trace.trace("foreground restored to user's window")
        except Exception:
            pass

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
            if self._value_length(box) == 0:
                return True
            box.type_keys(_combo(not primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._value_length(box) == 0:
                return True
            info = self.target.send_button_click(near_box=box)
            if info and not any(k in info[0].lower() for k in
                                ("voice", "record", "mic", "audio")):
                winapi.post_click(hwnd, info[1], info[2])
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                return self._value_length(box) == 0
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
                if self._value_length(box) == 0:
                    return True
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True
                info = self.target.send_button_click(near_box=box)
                if info and not any(k in info[0].lower() for k in
                                    ("voice", "record", "mic", "audio")):
                    winapi.post_click(hwnd, info[1], info[2])
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._value_length(box) == 0
                return False
        except Exception as e:
            trace.trace(f"B failed: {e}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)
