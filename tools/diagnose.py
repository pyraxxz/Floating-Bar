"""Read-only diagnostics + optional live send test for Floating Bar.

Run from the repo root:

    python tools/diagnose.py                         # window + compose + buttons
    python tools/diagnose.py --preflight             # read-only send readiness
    python tools/diagnose.py --send "test 123"       # run the hardened live send

The default and --preflight forms are completely read-only: they inspect
window geometry, control identifiers, focus ownership, and safety evidence —
never message content. The --send form actually sends text to the currently
open Telegram chat using the same hardened injector family as the production
orb.
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
from floatingbar.hardening import HardenedTelegramInjector
from floatingbar.preflight import run as run_preflight
from floatingbar.target import TelegramTarget, TelegramNotFound


def _print_preflight(result) -> None:
    print("Safe-send preflight")
    print(f"  ready={result.ready}")
    print(f"  telegram_hwnd={result.hwnd}  pid={result.pid}")
    print(
        f"  minimized={result.minimized}  scope_stable={result.scope_stable}"
    )
    print(
        f"  focused_hwnd={result.focused_hwnd} "
        f"focused_pid={result.focused_pid}"
    )
    print(f"  compose_click={result.compose_click}")
    if result.button_available:
        print(
            f"  send_candidate=name={result.send_name!r} "
            f"point={result.send_point}"
        )
    else:
        print("  send_candidate=none (posted Enter fallback is available)")
    if result.reasons:
        print("  notes:")
        for reason in result.reasons:
            print(f"    - {reason}")
    else:
        print("  notes: none")


def _run_full_diagnostic(target: TelegramTarget, hwnd: int) -> int:
    title = winapi.get_window_title(hwnd)
    pid = winapi.get_window_pid(hwnd)
    focused = winapi.get_focused_hwnd(hwnd)
    focused_pid = winapi.get_window_pid(focused) if focused else 0
    print(f"  hwnd={hwnd}  pid={pid}  title={title!r}")
    print(f"  focused_hwnd={focused}  focused_pid={focused_pid}")
    if focused and focused_pid != pid:
        print("  WARNING: focus is currently owned by another process.")

    print("\nScanning UIA tree for Edit controls ...")
    import pywinauto

    app = pywinauto.Application(backend="uia").connect(handle=hwnd)
    window = app.window(handle=hwnd).wrapper_object()
    try:
        edits = window.descendants(control_type="Edit")
    except Exception as e:
        print(f"  FAILED to enumerate: {e}")
        return 2

    if not edits:
        print("  no Edit controls — is a chat actually open?")
        return 2

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
        try:
            rid = tuple(edit.element_info.runtime_id)
        except Exception:
            rid = ()
        print(
            f"  Edit[{i}]: {size}  value_pattern={has_vp} "
            f"text_pattern={has_tp}  runtime_id={rid}"
        )

    try:
        box = target.compose_box()
        rect = box.rectangle()
        print(
            f"\nChosen compose box: {rect.width()}x{rect.height()} "
            f"at ({rect.left},{rect.top})"
        )
        print(
            f"  (compose rect: left={rect.left} top={rect.top} "
            f"right={rect.right} bottom={rect.bottom})"
        )
        point = target.compose_click_point(box)
        print(f"  posted compose click point={point}")
        try:
            compose_rid = tuple(box.element_info.runtime_id)
        except Exception:
            compose_rid = ()
        print(f"  compose runtime_id={compose_rid}")
    except TelegramNotFound as e:
        print(f"\nCompose box selection failed: {e}")
        return 3

    print("\nScanning for Button controls near the compose box ...")
    try:
        buttons = window.descendants(control_type="Button")
        window_rect = window.rectangle()
    except Exception as e:
        print(f"  enumeration failed: {e}")
        buttons = []
        window_rect = rect
    near = 0
    for b in buttons:
        try:
            r = b.rectangle()
            name = (b.element_info.name or "")
        except Exception:
            continue
        if r.right < rect.left - 60 or r.left > rect.right + 240:
            continue
        if r.bottom < rect.top - 40 or r.top > rect.bottom + 40:
            continue
        has_invoke = "yes"
        try:
            b.iface_invoke
        except Exception:
            has_invoke = "no"
        try:
            automation_id = (b.element_info.automation_id or "")
        except Exception:
            automation_id = ""
        evidence = TelegramTarget._button_evidence_score(
            b,
            r,
            name,
            rect,
            window_rect,
        )
        try:
            rid = tuple(b.element_info.runtime_id)
        except Exception:
            rid = ()
        print(
            f"  Button: name={name!r} at ({r.left},{r.top})-({r.right},{r.bottom}) "
            f"invoke_pattern={has_invoke} automation_id={automation_id!r} "
            f"evidence_score={evidence:.1f} runtime_id={rid}"
        )
        near += 1
    if not near:
        print(
            "  (no buttons near the compose — the send button may not "
            "be exposed as a Button control on this build)"
        )

    print(f"\nTrace log location: {trace.path()}")
    print(
        "(if a send fails in the app, open the trace folder from the "
        "orb's right-click menu and share the log)"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--preflight",
        action="store_true",
        help="run a read-only safe-send readiness check",
    )
    actions.add_argument("--send", metavar="TEXT", help="run a live send test")
    args = parser.parse_args()

    preferred_hwnd = winapi.get_foreground_window()
    target = TelegramTarget()

    if args.preflight:
        result = run_preflight(target, preferred_hwnd=preferred_hwnd)
        _print_preflight(result)
        print(f"\nTrace log location: {trace.path()}")
        return 0 if result.ready else 3

    print("Scanning for Telegram Desktop ...")
    target.refresh(preferred_hwnd=preferred_hwnd)
    hwnd = target.hwnd
    if not hwnd:
        print("  NOT FOUND: no telegram.exe top-level window.")
        print("  Is Telegram Desktop installed and running?")
        return 1

    status = _run_full_diagnostic(target, hwnd)
    if status != 0:
        return status

    if args.send:
        injector = HardenedTelegramInjector(target)
        try:
            result = injector.send(args.send, restore_hwnd=preferred_hwnd)
            print(f"  -> OK, hardened strategy used: {result}")
        except Exception as e:
            print(f"  -> FAILED: {e}")
            print(f"  (full stage-by-stage detail in {trace.path()})")
            return 4
    else:
        print(
            '\nAll good. Run a read-only readiness check with:  '
            'python tools/diagnose.py --preflight'
        )
        print(
            'Or test a live send with:  '
            'python tools/diagnose.py --send "test 123"'
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
