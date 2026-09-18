"""Create and validate the real-Windows smoke-test report.

Run from the repository root on Windows:

    python tools/smoke_report.py --init smoke-report.json
    python tools/smoke_report.py --validate smoke-report.json
    python tools/smoke_report.py --validate smoke-report.json --require-complete

The initializer combines the content-free Windows environment snapshot with
the declarative smoke matrix. Use --record to stamp a completed case without
hand-editing timestamps; on Windows, --record also captures a fresh,
content-free case-local environment snapshot for release-gate evidence. It
never reads or stores window titles, conversation names, message bodies, input
values, or clipboard contents.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from floatingbar.smoke_matrix import (
    build_report,
    completion_errors,
    environment_case_errors,
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


def _record_case_evidence(snapshot, tested_at: str) -> dict:
    """Return content-free environment evidence captured at case-record time."""
    evidence = {"recorded_at": tested_at}
    try:
        evidence["monitors"] = [
            {
                "index": int(monitor.index),
                "width": int(monitor.width),
                "height": int(monitor.height),
                "dpi_x": int(monitor.dpi_x),
                "dpi_y": int(monitor.dpi_y),
            }
            for monitor in snapshot.monitors
        ]
        evidence["adapters"] = [
            {
                "key": str(adapter.key),
                "observed_process_instances": [
                    {
                        "process_name": str(name).casefold(),
                        "process_start": int(start),
                    }
                    for name, start in adapter.observed_process_instances
                    if isinstance(start, int) and not isinstance(start, bool) and int(start) > 0
                ],
            }
            for adapter in snapshot.adapters
        ]
    except Exception:
        # Keep the timestamp so a later release-gate check can distinguish
        # attempted evidence capture from missing case evidence.
        pass
    return evidence


def _source_commit() -> str:
    """Return the exact Git commit used to create the smoke report."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1],
        )
    except Exception:
        return ""
    value = completed.stdout.strip()
    if len(value) != 40:
        return ""
    try:
        int(value, 16)
    except ValueError:
        return ""
    return value


def _init(path: Path) -> int:
    snapshot = capture_snapshot()
    environment = snapshot.to_dict()
    environment["source_commit"] = _source_commit()
    report = build_report(environment=environment)
    _write(path, report)
    summary = summarize_report(report)
    print(f"Created smoke report: {path}")
    print(
        "  cases={total} pending={pending}".format(
            total=summary["total"], pending=summary["pending"]
        )
    )
    print(f"  matrix_fingerprint={report['matrix_fingerprint']}")
    return 0


def _release_environment_errors(report: dict) -> tuple[str, ...]:
    """Return release-gate errors for the required real-Windows snapshot."""
    environment = report.get("environment")
    if not isinstance(environment, dict):
        return ("environment snapshot is missing",)
    platform_name = str(environment.get("platform", "")).strip().casefold()
    if platform_name != "windows":
        return ("environment snapshot is not a Windows validation snapshot",)
    required_fields = (
        "windows_release",
        "windows_version",
        "architecture",
        "python_version",
        "source_commit",
    )
    missing = tuple(
        field for field in required_fields if not str(environment.get(field, "")).strip()
    )
    if missing:
        return tuple(f"environment snapshot missing field: {field}" for field in missing)
    source_commit = str(environment.get("source_commit", "")).strip()
    if len(source_commit) != 40:
        return ("environment source_commit is not a full Git commit SHA",)
    try:
        int(source_commit, 16)
    except ValueError:
        return ("environment source_commit is not a valid Git commit SHA",)
    return ()


def _record(path: Path, case_id: str, result: str, force: bool) -> int:
    """Record one manual smoke result with an execution timestamp."""
    report = _load(path)
    errors = validate_report(report)
    if errors:
        print("Smoke report validation: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 2

    normalized_result = str(result or "").strip().upper()
    allowed = {"PASS", "FAIL", "BLOCKED"}
    if normalized_result not in allowed:
        print(
            "Smoke report record: FAIL — result must be one of PASS, FAIL, BLOCKED",
            file=sys.stderr,
        )
        return 2

    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        print("Smoke report record: FAIL — cases must be a list", file=sys.stderr)
        return 2

    selected = None
    for item in raw_cases:
        if isinstance(item, dict) and str(item.get("case_id", "")) == case_id:
            selected = item
            break
    if selected is None:
        print(f"Smoke report record: FAIL — unknown case_id: {case_id}", file=sys.stderr)
        return 2

    current = str(selected.get("result", "PENDING"))
    if current != "PENDING" and not force:
        print(
            f"Smoke report record: REFUSED — {case_id} is already {current}; "
            "use --force to replace an existing completed result",
            file=sys.stderr,
        )
        return 3

    selected["result"] = normalized_result
    selected["tested_at"] = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    try:
        snapshot = capture_snapshot()
        selected["evidence"] = _record_case_evidence(snapshot, selected["tested_at"])
    except Exception:
        selected["evidence"] = {"recorded_at": selected["tested_at"]}
    _write(path, report)
    print(
        f"Recorded {case_id}: result={normalized_result} "
        f"tested_at={selected['tested_at']}"
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
    print(f"  matrix_fingerprint={report['matrix_fingerprint']}")
    if require_complete:
        environment_errors = _release_environment_errors(report)
        if environment_errors:
            print("Release gate: BLOCKED — required Windows environment snapshot is incomplete:")
            for error in environment_errors:
                print(f"  - {error}")
            return 5
    if require_complete:
        completion_issues = completion_errors(report)
        if completion_issues:
            print("Release gate: BLOCKED — completed smoke cases are missing execution timestamps:")
            for error in completion_issues:
                print(f"  - {error}")
            return 3
        environment_case_issues = environment_case_errors(report)
        if environment_case_issues:
            print("Release gate: BLOCKED — smoke PASS results lack matching environment evidence:")
            for error in environment_case_issues:
                print(f"  - {error}")
            return 6
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
    actions.add_argument("--record", metavar="PATH", help="record one completed smoke case")
    parser.add_argument(
        "--case-id",
        help="case_id to update with --record",
    )
    parser.add_argument(
        "--result",
        choices=("PASS", "FAIL", "BLOCKED"),
        help="result to record with --record",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow --record to replace an already-completed case",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="treat pending cases, failures, or an incomplete Windows snapshot as a release-gate failure",
    )
    args = parser.parse_args()

    path = Path(args.init or args.validate or args.record)
    try:
        if args.init:
            if path.exists():
                print(f"Refusing to overwrite existing report: {path}", file=sys.stderr)
                return 2
            return _init(path)
        if args.record:
            if not args.case_id:
                parser.error("--case-id is required with --record")
            if not args.result:
                parser.error("--result is required with --record")
            return _record(path, args.case_id, args.result, args.force)
        return _validate(path, args.require_complete)
    except Exception as exc:
        print(
            "Smoke report operation failed safely "
            f"(exception={type(exc).__name__})",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())