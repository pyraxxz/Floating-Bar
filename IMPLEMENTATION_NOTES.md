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

The next layer is deliberately additive: `floatingbar/hardening.py` subclasses the established `TelegramInjector` instead of replacing it.

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

This keeps the core product invariant: do not turn an uncertain state into a potentially dangerous microphone click.

## Testing status

The GitHub connector has confirmed write access and the hardening changes are committed directly to `main`.

The current environment cannot execute the Windows UI integration itself: Telegram Desktop, Win32 message queues, UI Automation, and the Windows Tk environment are not available here. Therefore the important remaining validation is a real Windows run against the user's Telegram build.

Use the existing diagnostic tool after pulling the latest `main`:

```bat
python tools/diagnose.py
python tools/diagnose.py --send "test 123"
```

For a failure, the trace file is still the primary diagnostic artifact and intentionally records lengths/geometry/stage information rather than message content.

## Next engineering targets

1. Run v0.1.8 against the user's real Telegram build and inspect the trace.
2. If the initial posted compose click does not establish Qt's internal target, investigate the exact child/focus HWND exposed by `GetGUIThreadInfo` without introducing a foreground activation.
3. Improve Send-button identification using stable geometry/runtime IDs learned from the trace rather than relying increasingly on accessible names.
4. Add unit tests for the geometry scoring, nested-field detection, voice-button rejection, and unverified submission state machine so future changes do not regress the hard-won Telegram-specific behavior.
5. Add a Windows CI smoke-test layer that at minimum imports/compiles the package and builds the PyInstaller executable; UI automation remains a manual/integration test because it requires Telegram.
