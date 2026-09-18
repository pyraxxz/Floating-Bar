"""Read-only diagnostics + optional live send test for Floating Bar.

Run from the repo root:

    python tools/diagnose.py                         # window + compose + buttons
    python tools/diagnose.py --context              # non-content chat-row UIA probe
    python tools/diagnose.py --preflight             # read-only send readiness
    python tools/diagnose.py --preflight --json      # machine-readable readiness
    python tools/diagnose.py --send "test 123"       # guarded live send test

The default, --context, and --preflight forms are completely read-only: they
inspect window geometry, control identifiers, focus ownership, and safety
evidence — never message content. The --send form performs the same transaction
preparation used by the production orb, then sends text with the same
context-aware, scope-guarded injector family.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from floatingbar import trace
from floatingbar import winapi
from floatingbar.context import title_fingerprint
from floatingbar.context_injector import ContextGuardedRecoveryInjector
from floatingbar.preflight import run as run_preflight
from floatingbar.bound_target import BoundTelegramTarget
from floatingbar.transaction_coordinator import SendTransactionCoordinator, TransactionRejected
from floatingbar.target import TelegramTarget, TelegramNotFound
import config


PREFLIGHT_JSON_SCHEMA_VERSION = 2


def _context_protection_for_result(result) -> str:
    """Derive the context protection level, including legacy result doubles."""
    value = getattr(result, "context_protection", None)
    if value in {"guarded", "degraded", "blocked"}:
        return value
    if not bool(getattr(result, "ready", False)):
        return "blocked"
    if bool(getattr(result, "context_guard_available", False)) and bool(
        getattr(result, "context_stable", False)
    ):
        return "guarded"
    return "degraded"


def _reason_codes_for_result(result):
    """Return stable machine-readable reason codes, including legacy doubles."""
    return list(getattr(result, "reason_codes", ()) or ())


def _primary_reason_code_for_result(result) -> str:
    """Return the first machine-readable reason, or ``ok``."""
    value = getattr(result, "primary_reason_code", None)
    if isinstance(value, str) and value:
        return value
    codes = _reason_codes_for_result(result)
    return codes[0] if codes else "ok"


def _preflight_payload(result) -> dict:
    """Return only content-free fields suitable for machine processing."""
    payload = {
        "schema_version": PREFLIGHT_JSON_SCHEMA_VERSION,
        "status": result.status,
        "context_protection": _context_protection_for_result(result),
        "ready": bool(result.ready),
        "primary_reason_code": _primary_reason_code_for_result(result),
        "reason_codes": _reason_codes_for_result(result),
        "telegram_hwnd": int(result.hwnd),
        "pid": int(result.pid),
        "minimized": bool(result.minimized),
        "scope_stable": bool(result.scope_stable),
        "focused_hwnd": int(result.focused_hwnd),
        "focused_pid": int(result.focused_pid),
        "compose_click": list(result.compose_click) if result.compose_click else None,
        "submission_path": result.submission_path,
        "send_candidate": (
            {
                "name": result.send_name,
                "point": list(result.send_point),
                "evidence_score": float(result.send_evidence_score),
            }
            if result.button_available and result.send_point
            else None
        ),
        "context_guard_available": bool(result.context_guard_available),
        "context_stable": bool(result.context_stable),
        "compose_runtime_anchor_available": bool(
            result.context is not None and result.context.compose_runtime_id
        ),
        "reasons": list(result.reasons),
    }
    return payload


def _print_preflight(result, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(_preflight_payload(result), sort_keys=True))
        return

    print("Safe-send preflight")
    print(f"  status={result.status}  ready={result.ready}")
    print(f"  context_protection={_context_protection_for_result(result)}")
    print(f"  primary_reason_code={_primary_reason_code_for_result(result)}")
    print(f"  reason_codes={_reason_codes_for_result(result)}")
    print(f"  telegram_hwnd={result.hwnd}  pid={result.pid}")
    print(
        f"  minimized={result.minimized}  scope_stable={result.scope_stable}"
    )
    print(
        f"  focused_hwnd={result.focused_hwnd} "
        f"focused_pid={result.focused_pid}"
    )
    print(f"  compose_click={result.compose_click}")
    print(f"  submission_path={result.submission_path}")
    print(
        f"  context_guard_available={result.context_guard_available} "
        f"context_stable={result.context_stable}"
    )
    if result.context is not None:
        print(
            "  compose_runtime_anchor_available="
            f"{bool(result.context.compose_runtime_id)}"
        )
    if result.button_available:
        print(
            f"  send_candidate=name={result.send_name!r} "
            f"point={result.send_point} "
            f"evidence_score={result.send_evidence_score:.1f}"
        )
    else:
        print("  send_candidate=none (posted Enter fallback is available)")
    if result.reasons:
        print("  notes:")
        for reason in result.reasons:
            print(f"    - {reason}")
    else:
        print("  notes: none")


def _window_context_summary(hwnd: int) -> dict:
    """Return content-free window context metadata for diagnostics output."""
    title = winapi.get_window_title(hwnd) or ""
    return {
        "title_present": bool(title.strip()),
        "title_fingerprint": title_fingerprint(title),
    }


def _is_telegram_window(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        pid = winapi.get_window_pid(hwnd)
        image = winapi.get_process_image_name(pid)
        base = image.rsplit("\\", 1)[-1] if image else ""
        if base and config.PROCESS_NAME_RE.search(base):
            return True
        title = winapi.get_window_title(hwnd)
        return bool(title and config.TITLE_FALLBACK_RE.search(title))
    except Exception:
        return False


def _run_context_diagnostic(hwnd: int) -> int:
    """Inspect content-free ListItem structure without selecting or reading text."""
    print("Telegram UIA chat-context probe (read-only)")
    print(f"  hwnd={hwnd}  pid={winapi.get_window_pid(hwnd)}")

    try:
        import pywinauto

        app = pywinauto.Application(backend="uia").connect(handle=hwnd)
        window = app.window(handle=hwnd).wrapper_object()
        window_rect = window.rectangle()
        items = window.descendants(control_type="ListItem")
    except Exception as exc:
        print(
            "  FAILED to enumerate ListItem controls safely "
            f"(exception={trace.exception_name(exc)})"
        )
        return 2

    width = max(1, window_rect.width())
    left_cutoff = window_rect.left + int(width * 0.60)
    candidates = []
    for item in items:
        try:
            rect = item.rectangle()
            runtime_id = tuple(item.element_info.runtime_id)
            name = item.element_info.name or ""
            automation_id = item.element_info.automation_id or ""
        except Exception:
            continue

        try:
            selected = bool(item.is_selected())
        except Exception:
            selected = None
            try:
                selection = item.iface_selection_item
                selected = bool(selection.CurrentIsSelected)
            except Exception:
                pass

        left_pane_candidate = rect.left < left_cutoff and rect.width() > 80
        if selected or left_pane_candidate:
            candidates.append(
                (
                    rect,
                    selected,
                    runtime_id,
                    title_fingerprint(name),
                    automation_id,
                    left_pane_candidate,
                )
            )

    print(f"  ListItem controls={len(items)}")
    print(f"  reported candidates={len(candidates)}")
    if not candidates:
        print("  no candidate ListItem controls found")
        print("  (Telegram may not expose chat rows through UIA on this build)")
        return 0

    for i, (rect, selected, runtime_id, name_fp, automation_id, left_pane) in enumerate(candidates):
        print(
            f"  ListItem[{i}]: selected={selected} left_pane_candidate={left_pane} "
            f"at ({rect.left},{rect.top})-({rect.right},{rect.bottom}) "
            f"automation_id={automation_id!r} runtime_id={runtime_id} "
            f"name_fp={name_fp or 'none'}"
        )

    selected_left = [
        candidate for candidate in candidates if candidate[1] is True and candidate[5]
    ]
    print(f"  selected_left_pane_candidates={len(selected_left)}")
    if len(selected_left) == 1:
        print("  context-anchor candidate: unique selected left-pane ListItem")
    elif len(selected_left) > 1:
        print("  context-anchor candidate: ambiguous (multiple selected left-pane items)")
    else:
        print("  context-anchor candidate: none")

    print(f"\nTrace log location: {trace.path()}")
    print("(no message text or raw chat-row names are written by this probe)")
    return 0


def _run_full_diagnostic(target: TelegramTarget, hwnd: int) -> int:
    context_summary = _window_context_summary(hwnd)
    pid = winapi.get_window_pid(hwnd)
    focused = winapi.get_focused_hwnd(hwnd)
    focused_pid = winapi.get_window_pid(focused) if focused else 0
    print(f"  hwnd={hwnd}  pid={pid}")
    print(
        "  title_present={title_present}  title_fingerprint={title_fingerprint}"
        .format(**context_summary)
    )
    print(f"  focused_hwnd={focused}  focused_pid={focused_pid}")
    if focused and focused_pid != pid:
        print("  WARNING: focus is currently owned by another process.")

    print("\nScanning UIA tree for Edit controls ...")
    import pywinauto

    app = pywinauto.Application(backend="uia").connect(handle=hwnd)
    window = app.window(handle=hwnd).wrapper_object()
    try:
        edits = window.descendants(control_type="Edit")
    except Exception as exc:
        print(
            "  FAILED to enumerate Edit controls safely "
            f"(exception={trace.exception_name(exc)})"
        )
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
    except Exception as exc:
        print(
            "  button enumeration failed safely "
            f"(exception={trace.exception_name(exc)})"
        )
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


def _run_guarded_send(target: TelegramTarget, text: str, preferred_hwnd: int) -> int:
    """Use the same transaction preparation and guarded injector as production."""
    bound = BoundTelegramTarget(target)
    preferred = preferred_hwnd if _is_telegram_window(preferred_hwnd) else 0
    coordinator = SendTransactionCoordinator(bound)
    try:
        try:
            prepared = coordinator.prepare(
                text=text,
                attempt_id=1,
                preferred_hwnd=preferred,
                restore_hwnd=preferred_hwnd,
            )
        except TransactionRejected as exc:
            if exc.preflight is not None:
                _print_preflight(exc.preflight)
            print("\n  -> SEND REFUSED: transaction preparation was blocked safely.")
            print(f"  -> reason: {exc}")
            return 3

        _print_preflight(prepared.preflight)
        injector = ContextGuardedRecoveryInjector(bound)
        injector.set_window_context(prepared.attempt.context)
        result = injector.send(
            prepared.attempt.text,
            restore_hwnd=prepared.attempt.restore_hwnd,
        )
        print(f"  -> OK, context-guarded strategy used: {result}")
        return 0
    except Exception as exc:
        print(
            "  -> FAILED safely "
            f"(exception={trace.exception_name(exc)})"
        )
        print(f"  (full stage-by-stage detail in {trace.path()})")
        return 4
    finally:
        bound.release()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--context",
        action="store_true",
        help="inspect content-free chat-row UIA structure",
    )
    actions.add_argument(
        "--preflight",
        action="store_true",
        help="run a read-only safe-send readiness check",
    )
    actions.add_argument("--send", metavar="TEXT", help="run a guarded live send test")
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --preflight, emit a content-free JSON report",
    )
    args = parser.parse_args()

    if args.json and not args.preflight:
        parser.error("--json is supported only with --preflight")

    preferred_hwnd = winapi.get_foreground_window()
    target = TelegramTarget()

    if args.preflight:
        result = run_preflight(target, preferred_hwnd=preferred_hwnd)
        _print_preflight(result, json_output=args.json)
        if not args.json:
            print(f"\nTrace log location: {trace.path()}")
        return 0 if result.ready else 3

    print("Scanning for Telegram Desktop ...")
    target.refresh(preferred_hwnd=preferred_hwnd)
    hwnd = target.hwnd
    if not hwnd:
        print("  NOT FOUND: no telegram.exe top-level window.")
        print("  Is Telegram Desktop installed and running?")
        return 1

    if args.context:
        return _run_context_diagnostic(hwnd)

    if args.send:
        return _run_guarded_send(target, args.send, preferred_hwnd)

    status = _run_full_diagnostic(target, hwnd)
    if status != 0:
        return status

    print(
        '\nAll good. Run a read-only readiness check with:  '
        'python tools/diagnose.py --preflight'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
