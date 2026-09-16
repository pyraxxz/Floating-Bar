"""Floating Bar — entry point.

Single-instance guarded; on a second launch the process exits silently.
"""

import sys
import traceback


def main() -> None:
    import config
    from floatingbar import dpi
    from floatingbar import winapi  # raises ImportError on non-Windows

    if not winapi.acquire_single_instance(config.SINGLE_INSTANCE_MUTEX):
        sys.exit(0)  # already running — stay quiet

    # Establish DPI awareness before Tk creates any windows so UIA geometry,
    # Tk coordinates, and posted client clicks stay on the same scale across
    # mixed-DPI monitors. Failure is non-fatal for restricted environments.
    dpi.enable_per_monitor_awareness()

    # Production overlay: hardened invisible injection, guarded opt-in
    # recovery, explicit retry UX, non-content Telegram context checks, and
    # an immutable per-attempt Telegram target lease.
    from floatingbar.bound_context_overlay import OrbRelayWindow
    from floatingbar.hotkey import GlobalHotkey, HotkeySpec

    app = OrbRelayWindow()
    hotkey = GlobalHotkey(
        HotkeySpec(config.HOTKEY_MODIFIERS, config.HOTKEY_VIRTUAL_KEY),
        on_trigger=app._expand,
        tk_root=app,
    )
    hotkey.start()
    try:
        app.run()
    except Exception:
        # Launched via pythonw.exe there is no console — make a fatal
        # crash visible instead of dying silently. (Per-message failures
        # never use popups; this is only for unrecoverable startup/loop
        # crashes.)
        err = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "Floating Bar crashed:\n\n" + err[-800:], "Floating Bar", 0x10
            )
        except Exception:
            pass
        raise
    finally:
        hotkey.stop()


if __name__ == "__main__":
    main()
