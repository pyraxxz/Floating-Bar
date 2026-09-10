"""Read-only diagnostics + optional live send test for Floating Bar.

Run from the repo root:

    python tools/diagnose.py                     # window + compose box info
    python tools/diagnose.py --send "test 123"   # run the real cascade once

The first form is completely read-only (it only inspects window geometry
and control types — never message content). The second form actually
sends text to the currently open Telegram chat, exactly like the app
does on Enter.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from floatingbar import winapi
from floatingbar.injector import TelegramInjector
from floatingbar.target import TelegramTarget, TelegramNotFound


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", metavar="TEXT", help="run a live send test")
    args = parser.parse_args()

    print("Scanning for Telegram Desktop ...")
    target = TelegramTarget()
    target.refresh()
    hwnd = target.hwnd
    if not hwnd:
        print("  NOT FOUND: no telegram.exe top-level window.")
        print("  Is Telegram Desktop installed and running?")
        sys.exit(1)

    title = winapi.get_window_title(hwnd)
    pid = winapi.get_window_pid(hwnd)
    print(f"  hwnd={hwnd}  pid={pid}  title={title!r}")

    print("\nScanning UIA tree for Edit controls ...")
    import pywinauto

    app = pywinauto.Application(backend="uia").connect(handle=hwnd)
    window = app.window(handle=hwnd).wrapper_object()
    try:
        edits = window.descendants(control_type="Edit")
    except Exception as e:
        print(f"  FAILED to enumerate: {e}")
        sys.exit(2)

    if not edits:
        print("  no Edit controls — is a chat actually open?")
        sys.exit(2)

    for i, edit in enumerate(edits):
        try:
            rect = edit.rectangle()
            size = f"{rect.width()}x{rect.height()} at ({rect.left},{rect.top})"
        except Exception:
            size = "geometry unavailable"
        readonly = "?"
        try:
            readonly = bool(edit.iface_value.CurrentIsReadOnly)
        except Exception:
            pass
        has_vp = "yes"
        try:
            edit.iface_value
        except Exception:
            has_vp = "no"
        print(f"  Edit[{i}]: {size}  readonly={readonly}  value_pattern={has_vp}")

    try:
        best = target.compose_box()
        rect = best.rectangle()
        print(
            f"\nChosen compose box: {rect.width()}x{rect.height()} "
            f"at ({rect.left},{rect.top})"
        )
    except TelegramNotFound as e:
        print(f"\nCompose box selection failed: {e}")
        sys.exit(3)

    if args.send:
        print(f'\nSending: {args.send!r}')
        injector = TelegramInjector(target)
        try:
            result = injector.send(args.send)
            print(f"  -> OK, strategy used: {result}")
        except Exception as e:
            print(f"  -> FAILED: {e}")
            sys.exit(4)
    else:
        print('\nAll good. Test a live send with:  python tools/diagnose.py --send "test 123"')


if __name__ == "__main__":
    main()
