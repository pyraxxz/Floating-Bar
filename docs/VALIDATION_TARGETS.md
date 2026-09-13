# Validation targets

## Current Telegram Desktop target

The next real-desktop acceptance pass should use the current Windows Telegram Desktop stable build available at validation time. As of September 13, 2026, that target is **7.2.8**.

The project must not assume that a UIA structure observed on an older Telegram build is still authoritative. The `--context` diagnostic is intentionally read-only and exists to capture the actual selected `ListItem` structure exposed by the installed build before production chat-switch heuristics are tightened further.

## Read-only evidence collection

Run these from the repository root on the Windows test machine:

```bat
python tools/diagnose.py --preflight
python tools/diagnose.py --preflight --json
python tools/diagnose.py --context
python tools/diagnose.py
```

The `--context` probe reports:

- selected-state availability for `ListItem` controls;
- left-pane candidate geometry;
- UIA runtime IDs;
- automation IDs;
- one-way name fingerprints rather than raw chat names.

It never clicks or changes selection, and its output intentionally omits raw chat-row names and message content.

## Production acceptance cases

The release gate remains broader than a single successful send:

1. One normal invisible send in the intended chat.
2. Two Telegram windows open, with the intended window selected when the orb opens.
3. Switch the active chat before sending and verify that the guard blocks when Telegram exposes a detectable context change.
4. Switch chats inside the same generic-title/UIA configuration and verify degraded behavior rather than a false claim of exact identity.
5. Restart Telegram between preflight and send; verify that the original HWND/PID lease prevents delivery to the replacement window.
6. Minimize Telegram; verify preflight refuses the send.
7. Force an unverified outcome and verify that the UI does not offer an automatic retry.
8. Cause a genuine failure and verify that explicit retry preserves the intended Telegram target and never submits automatically.
9. Verify send-button safety against voice/mic and unrelated controls.
10. Verify emoji, intentional leading/trailing whitespace, repeated sends, and mixed-DPI/multi-monitor placement.
11. Run `--context` before and after a chat switch and retain the content-free output for UIA tuning.

## Interpretation rule

A passing automated suite does not prove the Windows/Telegram UI contract. A real-desktop pass must record the Telegram version, Windows DPI/display arrangement, number of Telegram windows, and the content-free preflight/context output. Those traces should drive any further production heuristic changes.
