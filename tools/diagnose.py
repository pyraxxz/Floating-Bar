"""Read-only diagnostics + optional live send test for Floating Bar.

Run from the repo root:

    python tools/diagnose.py                     # window + compose + buttons
    python tools/diagnose.py --send "test 123"   # run the real cascade once

The first form is completely read-only (it inspects window geometry,
control types and names — never message content). The second form
actually sends text to the currently open Telegram chat, exactly like
the app does on Enter, and prints which submit stage succeeded.
Everything it reports is also written to the app's trace log:

    %APPDATA%\\FloatingBar\\trace.log
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from floatingbar import trace
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
        has_vp = "yes"
        try:
            edit.iface_value
        except Exception:
            has_vp = "no"
        has_tp = "yes"
        try:
            edit.iface_text
        except Exception:
            has_tp = "no"
        print(f"  Edit[{i}]: {size}  value_pattern={has_vp} text_pattern={has_tp}")

    try:
        box = target.compose_box()
        rect = box.rectangle()
        print(
            f"\nChosen compose box: {rect.width()}x{rect.height()} "
            f"at ({rect.left},{rect.top})"
        )
        print(f"  (compose rect: left={rect.left} top={rect.top} "
              f"right={rect.right} bottom={rect.bottom})")
    except TelegramNotFound as e:
        print(f"\nCompose box selection failed: {e}")
        sys.exit(3)

    print("\nScanning for Button controls near the compose box ...")
    try:
        buttons = window.descendants(control_type="Button")
    except Exception as e:
        print(f"  enumeration failed: {e}")
        buttons = []
    near = 0
    for b in buttons:
        try:
            r = b.rectangle()
            name = (b.element_info.name or "")
        except Exception:
            continue
        # within/near the compose area's right end
        if r.right < rect.left - 60 or r.left > rect.right + 240:
            continue
        if r.bottom < rect.top - 40 or r.top > rect.bottom + 40:
            continue
        has_invoke = "yes"
        try:
            b.iface_invoke
        except Exception:
            has_invoke = "no"
        print(f"  Button: name={name!r} at ({r.left},{r.top})-({r.right},{r.bottom})"
              f"  invoke_pattern={has_invoke}")
        near += 1
    if not near:
        print("  (no buttons near the compose — the send button may not "
              "be exposed as a Button control on this build)")

    print(f"\nTrace log location: {trace.path()}")
    print("(if a send fails in the app, open the trace folder from the "
          "orb's right-click menu and share the log)")

    if args.send:
        print(f"\nSending: {args.send!r}")
        injector = TelegramInjector(target)
        try:
            result = injector.send(args.send)
            print(f"  -> OK, strategy used: {result}")
        except Exception as e:
            print(f"  -> FAILED: {e}")
            print(f"  (full stage-by-stage detail in {trace.path()})")
            sys.exit(4)
    else:
        print('\nAll good. Test a live send with:  python tools/diagnose.py --send "test 123"')


if __name__ == "__main__":
    main()
