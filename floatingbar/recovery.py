"""Scope-aware variants of the opt-in recovery strategies.

The normal invisible path already lives in :mod:`floatingbar.hardening`.
This module extends that class only for the optional focus-steal and
clipboard-recovery strategies, adding target-scope checks before each
critical interaction with the Telegram window.
"""

import time

import config
from . import clipboard_guard
from . import trace
from . import winapi
from .hardening import HardenedTelegramInjector, _is_voice_name
from .injector import InjectionFailed, _combo


class ScopeGuardedRecoveryInjector(HardenedTelegramInjector):
    """Hardened injector with per-action guards in opt-in recovery."""

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        """Capture one immutable Telegram scope for the whole send transaction."""
        hwnd = self.target.hwnd or 0
        pid = winapi.get_window_pid(hwnd) if hwnd else 0
        self._recovery_scope = (hwnd, pid)
        try:
            return super().send(text, restore_hwnd=restore_hwnd)
        finally:
            self._recovery_scope = None

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """Opt-in foreground recovery with a guard before every target action."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            self._assert_target_scope(hwnd, "before focus-steal restore")
            winapi.ensure_restored(hwnd)

            self._assert_target_scope(hwnd, "before focus-steal foreground")
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)

            self._assert_target_scope(hwnd, "before focus-steal focus")
            box.set_focus()

            self._assert_target_scope(hwnd, "before focus-steal primary Enter")
            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._value_length(box) == 0:
                return True

            self._assert_target_scope(hwnd, "before focus-steal alternate Enter")
            box.type_keys(_combo(not primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._value_length(box) == 0:
                return True

            self._assert_target_scope(hwnd, "before focus-steal Send discovery")
            info = self.target.send_button_click(near_box=box)
            if info and not _is_voice_name(info[0]):
                self._assert_target_scope(hwnd, "before focus-steal Send click")
                winapi.post_click(hwnd, info[1], info[2])
                verified = self._poll_compose_clear(
                    lambda: self._value_length(box)
                )
                return verified is True
            return False
        except InjectionFailed:
            raise
        except Exception as exc:
            trace.trace(f"scope-guarded focus-steal submit failed: {exc}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """Opt-in clipboard recovery with a fixed send-transaction scope."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            with clipboard_guard.preserved_clipboard(
                retries=config.CLIPBOARD_RETRIES,
                delay=config.CLIPBOARD_RETRY_DELAY_S,
            ):
                fixed_scope = getattr(self, "_recovery_scope", None)
                if fixed_scope and fixed_scope[0] and fixed_scope[1]:
                    hwnd = fixed_scope[0]
                else:
                    hwnd = self.target.hwnd or 0

                self._assert_target_scope(hwnd, "before clipboard recovery")
                winapi.ensure_restored(hwnd)

                self._assert_target_scope(hwnd, "before clipboard recovery foreground")
                if not winapi.set_foreground_window(hwnd):
                    return False
                time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)

                self._assert_target_scope(hwnd, "before clipboard recovery focus")
                box.set_focus()

                self._assert_target_scope(hwnd, "before clipboard recovery clear")
                box.type_keys("^a", pause=0.01)
                box.type_keys("{DEL}", pause=0.01)

                self._assert_target_scope(hwnd, "before clipboard recovery clipboard write")
                if not clipboard_guard.set_text(
                    text,
                    retries=config.CLIPBOARD_RETRIES,
                    delay=config.CLIPBOARD_RETRY_DELAY_S,
                ):
                    raise InjectionFailed(
                        "The clipboard could not be prepared safely; paste recovery was refused."
                    )

                self._assert_target_scope(hwnd, "before clipboard recovery paste")
                box.type_keys("^v", pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)

                self._assert_target_scope(hwnd, "before clipboard recovery primary Enter")
                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True

                self._assert_target_scope(hwnd, "before clipboard recovery alternate Enter")
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True

                self._assert_target_scope(hwnd, "before clipboard recovery Send discovery")
                info = self.target.send_button_click(near_box=box)
                if info and not _is_voice_name(info[0]):
                    self._assert_target_scope(hwnd, "before clipboard recovery Send click")
                    winapi.post_click(hwnd, info[1], info[2])
                    verified = self._poll_compose_clear(
                        lambda: self._value_length(box)
                    )
                    return verified is True
                return False
        except InjectionFailed:
            raise
        except Exception as exc:
            trace.trace(f"scope-guarded clipboard recovery failed: {exc}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)
