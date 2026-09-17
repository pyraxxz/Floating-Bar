"""Create and validate the real-Windows smoke-test report.

Run from the repository root on Windows:

    python tools/smoke_report.py --init smoke-report.json
    python tools/smoke_report.py --validate smoke-report.json
    python tools/smoke_report.py --validate smoke-report.json --require-complete

The initializer combines the content-free Windows environment snapshot with
the declarative smoke matrix. It never reads or stores window titles,
conversation names, message bodies, input values, or clipboard contents.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from floatingbar.smoke_matrix import (
    build_report,
    pending_case_ids,
    summarize_report,
    validate_report,
)
from floatingbar.windows_validation import capture_snapshot


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("smoke report root must be an object")
    return payload


def _write(path: Path, report: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _init(path: Path) -> int:
    snapshot = capture_snapshot()
    report = build_report(environment=snapshot.to_dict())
    _write(path, report)
    summary = summarize_report(report)
    print(f"Created smoke report: {path}")
    print(
        "  cases={total} pending={pending}".format(
            total=summary["total"], pending=summary["pending"]
        )
    )
    return 0


def _validate(path: Path, require_complete: bool) -> int:
    report = _load(path)
    errors = validate_report(report)
    if errors:
        print("Smoke report validation: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 2

    summary = summarize_report(report)
    print(
        "Smoke report validation: PASS "
        f"total={summary['total']} pass={summary['pass']} "
        f"fail={summary['fail']} blocked={summary['blocked']} "
        f"pending={summary['pending']}"
    )
    if require_complete and summary["pending"]:
        print("Release gate: BLOCKED — unresolved smoke cases remain:")
        for case_id in pending_case_ids(report):
            print(f"  - {case_id}")
        return 3
    if summary["fail"]:
        print("Release gate: FAIL — smoke failures remain unresolved")
        return 4 if require_complete else 0
    if require_complete:
        print("Release gate: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--init", metavar="PATH", help="create a fresh smoke report")
    actions.add_argument("--validate", metavar="PATH", help="validate an existing smoke report")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="treat pending cases or failures as a release-gate failure",
    )
    args = parser.parse_args()

    path = Path(args.init or args.validate)
    try:
        if args.init:
            if path.exists():
                print(f"Refusing to overwrite existing report: {path}", file=sys.stderr)
                return 2
            return _init(path)
        return _validate(path, args.require_complete)
    except Exception as exc:
        print(f"Smoke report operation failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
