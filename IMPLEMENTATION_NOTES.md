# Floating Bar implementation notes

## Current baseline

The repository's v0.1.7 baseline came from the real Telegram traces collected during the earlier implementation work.

Important established behavior:

- Telegram is located primarily by process image name rather than window title.
- Text injection uses posted `WM_CHAR` UTF-16 code units; UIA `ValuePattern.SetValue` is deliberately not used.
- The compose can expose nested `Edit` controls. The injector audits value lengths and can remember the inner text-holding field for the session.
- Submission prefers an invisible posted click on Telegram's Send button and falls back to posted Enter combinations when a button cannot be located.
- Minimized Telegram is rejected rather than pretending the send succeeded.
- Focus-stealing and clipboard-based recovery remain opt-in through `ALLOW_FOCUS_STEAL=False`.
- Clipboard recovery preserves HGLOBAL-backed formats rather than performing a text-only clipboard round trip.

## v0.1.8 hardening

`floatingbar/hardening.py` subclasses the established `TelegramInjector` and is wired directly into `overlay.py`, so the hardened path is the path used by the application.

### Phase 0 — deterministic compose targeting

Before posting text, the hardened injector computes the selected compose control's client-space center and posts a mouse click there. This addresses a weakness in v0.1.7: the code documented a compose-click step but the primary landing path posted `WM_CHAR` directly without actually performing that initial click.

The real mouse is not moved. No UIA write is performed. If geometry cannot be obtained, the original injector's audit/retry path remains available.

### Safer unverified submission

The original verified path is retained unchanged. When the audit confirms that the text is in the compose, the existing rightmost-button heuristic is still used because the compose channel provides the safety signal.

When the audit cannot verify the landing location:

- a button explicitly named `Send` may be clicked;
- voice/record/mic/audio controls are always rejected;
- an unnamed or otherwise ambiguous button is not clicked blindly;
- the code falls back to posted Enter combinations instead.

This preserves the core safety invariant: uncertain state must not become a potentially dangerous microphone click.

### Win32 post reliability

`floatingbar/winapi.py` now checks the return value of every safety-critical `PostMessageW` call. Invalid or rejected target windows raise an error instead of being reported as a successful injection stage. UTF-16 `WM_CHAR` behavior is retained.

### Clipboard failure semantics

The clipboard guard now distinguishes `snapshot() == []` (a successfully opened empty/unsupported clipboard) from `snapshot() is None` (clipboard could not be opened). Recovery therefore never converts a failed snapshot into an instruction to clear the clipboard.

## Regression tests and CI

`tests/test_hardening.py` covers nested-field geometry, voice-button rejection, explicit Send detection, deterministic compose-targeting order, and the unverified submission state machine.

`.github/workflows/ci.yml` runs on Windows, compiles the source tree, executes the unittest suite, and builds `FloatingBar.exe` with PyInstaller. The existing release workflow remains responsible for tag-based release builds.

The current environment still cannot execute the Windows/Telegram integration itself. The important remaining validation is a real Windows run against the user's Telegram build.

Use the diagnostic tool after pulling the latest `main`:

```bat
python tools/diagnose.py
python tools/diagnose.py --send "test 123"
```

For a failure, the trace file remains the primary diagnostic artifact and intentionally records lengths/geometry/stage information rather than message content.

## Next engineering targets

1. Run v0.1.8 against the real Telegram build and inspect the trace.
2. If the initial posted compose click does not establish Qt's internal target, investigate the exact child/focus HWND exposed by `GetGUIThreadInfo` without introducing foreground activation.
3. Replace heuristic Send-button selection with stable geometry/runtime-ID evidence gathered from real traces where possible.
4. Extend regression coverage around stale UIA elements, repeated sends, emoji/surrogate-pair text, minimized Telegram, and window-restart behavior.
5. Keep UI integration as a manual test because it requires an actual Windows desktop and Telegram instance.
