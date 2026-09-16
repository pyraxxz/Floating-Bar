"""Read-only Telegram conversation-attention diagnostic.

Run from the repo root:

    python tools/diagnose_attention.py

The diagnostic reports only content-free attention state, structural identity,
geometry, and a fingerprint of each chat-row name. It never prints message
previews/bodies and never clicks, focuses, or changes Telegram.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from floatingbar import trace, winapi
from floatingbar.context import title_fingerprint
from floatingbar.telegram_chats import enumerate_telegram_chats
import config


def _find_telegram_window() -> int:
    foreground = winapi.get_foreground_window()
    if foreground:
        try:
            pid = winapi.get_window_pid(foreground)
            image = winapi.get_process_image_name(pid)
            base = image.rsplit("\\", 1)[-1] if image else ""
            if base and config.PROCESS_NAME_RE.search(base):
                return foreground
        except Exception:
            pass

    candidates = []
    for hwnd in winapi._enum_windows():
        try:
            pid = winapi.get_window_pid(hwnd)
            image = winapi.get_process_image_name(pid)
            base = image.rsplit("\\", 1)[-1] if image else ""
            if base and config.PROCESS_NAME_RE.search(base):
                candidates.append(hwnd)
        except Exception:
            continue
    return candidates[0] if candidates else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=12, help="maximum chat rows to inspect")
    args = parser.parse_args()

    hwnd = _find_telegram_window()
    if not hwnd:
        print("Telegram window not found.")
        return 2

    pid = winapi.get_window_pid(hwnd)
    print("Telegram attention probe (read-only)")
    print(f"  hwnd={hwnd} pid={pid}")
    print(f"  title_fingerprint={title_fingerprint(winapi.get_window_title(hwnd) or '') or 'none'}")

    rows = enumerate_telegram_chats(hwnd, limit=max(1, min(args.limit, 32)))
    print(f"  rows={len(rows)}")
    if not rows:
        print("  No UIA chat rows were exposed on this Telegram build.")
        print(f"  trace={trace.path()}")
        return 0

    for index, row in enumerate(rows):
        identity = "runtime" if row.runtime_id is not None else "structural"
        name_fp = title_fingerprint(row.name) or "none"
        print(
            f"  row[{index}] attention={row.attention.state.value} "
            f"source={row.attention.source} selected={row.selected} "
            f"identity={identity} geometry=({row.left},{row.top})-({row.right},{row.bottom}) "
            f"name_fp={name_fp}"
        )

    print(f"  trace={trace.path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
