# Floating Bar implementation notes

## Current baseline

The repository evolved from the real Telegram traces collected during the earlier implementation work. The production orb uses the hardened injector path rather than the original injector directly.

Established behavior:

- Telegram is located primarily by process image name rather than window title.
- Text injection uses posted `WM_CHAR` UTF-16 code units; UIA `ValuePattern.SetValue` is deliberately not used.
- The compose can expose nested `Edit` controls. The injector audits value lengths and remembers the inner text-holding field for the session.
- Submission prefers an invisible posted click on Telegram's Send button and falls back to posted Enter combinations when a button cannot be located.
- Minimized Telegram is rejected rather than pretending the send succeeded.
- Focus-stealing and clipboard-based recovery remain opt-in through `ALLOW_FOCUS_STEAL=False`.
- Clipboard recovery preserves HGLOBAL-backed formats and distinguishes clipboard-open failure from an actually empty clipboard.

## v0.1.9 hardening

### Focused-child injection

After the hardened injector posts its deterministic compose click, it asks `GetGUIThreadInfo` for Telegram's focused child HWND. When that HWND belongs to Telegram's process, `WM_CHAR` is posted directly to it. If that route is rejected, the injector falls back to the top-level Telegram HWND.

This narrows dependence on Qt's top-level event routing while retaining invisible background behavior.

### Compose-aware audit selection

The audit considers all Edit controls but prefers positive-value controls that geometrically overlap the compose selected for the send. This prevents a pre-filled search field from winning merely because it appears first in the UI Automation tree.

Among overlapping positive-value controls, the smaller control is preferred because the real inner compose Edit observed in earlier traces is slightly smaller than its wrapper.

### Diagnostics parity

`tools/diagnose.py --send` uses the same `HardenedTelegramInjector` as the production overlay. Diagnostic output includes the focused HWND, compose click point, runtime IDs, and whether nearby buttons expose InvokePattern.

### Release/deployment

Every push to `main` checks `floatingbar.__version__`. When that version has not been released yet, the release workflow creates the matching `vX.Y.Z` tag, runs Windows compile/tests/build, and publishes `FloatingBar.exe`. Existing released versions are not rebuilt on ordinary maintenance commits.

## Validation

Windows CI compiles the source tree, runs the unittest suite, and builds the PyInstaller executable. The release pipeline performs the same validation before publishing a versioned EXE.

The current development environment cannot execute the final Windows/Telegram UI integration itself. The trace log intentionally records lengths, geometry, runtime IDs, stages, and booleans — never message content.

## Next targets

1. Validate focused-child routing against multiple Telegram window states and versions.
2. Replace increasingly heuristic Send-button selection with a scored evidence model using geometry, runtime IDs, control patterns, and explicit names.
3. Add a bounded submission state machine that distinguishes posted, observed, and verified outcomes without false-positive success.
4. Extend regression coverage around runtime-ID churn, stale UIA elements, repeated sends, emoji/surrogate-pair text, minimized Telegram, and Telegram restarts.
5. Generalize the target abstraction to other Windows background apps after Telegram behavior is stable.
