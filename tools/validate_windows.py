"""Capture a content-free Windows validation snapshot.

Run from the repository root on Windows:

    python tools/validate_windows.py
    python tools/validate_windows.py --json
    python tools/validate_windows.py --json --output smoke-snapshot.json

The report records OS/runtime characteristics and which supported application
processes currently expose user-facing windows. It never records window titles,
chat names, message content, input values, or clipboard contents.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from floatingbar.windows_validation import capture_snapshot, format_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable content-free JSON snapshot",
    )
    parser.add_argument(
        "--output",
        help="write the content-free JSON snapshot to this path",
    )
    args = parser.parse_args()

    try:
        snapshot = capture_snapshot()
    except Exception as exc:
        print(f"Windows validation could not run safely: {exc}", file=sys.stderr)
        return 2

    payload = snapshot.to_dict()
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"Wrote content-free validation snapshot to {args.output}")

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif not args.output:
        print(format_report(snapshot))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
