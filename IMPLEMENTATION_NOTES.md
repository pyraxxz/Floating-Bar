# Floating Bar implementation notes

## Current baseline

The repository evolved from the real Telegram traces collected during the earlier implementation work. The production orb uses the hardened injector path rather than the original injector directly.

Established behavior:

- Telegram is located primarily by process image name rather than window title.
- Text injection uses posted `WM_CHAR` UTF-16 code units; UIA `ValuePattern.SetValue` is deliberately not used.
- The compose can expose nested `Edit` controls. The injector audits value lengths and remembers the inner text-holding field for the current Telegram window/process.
- Submission prefers an invisible posted click on Telegram's Send button and falls back to posted Enter combinations when a button cannot be located.
- Minimized Telegram is rejected rather than pretending the send succeeded.
- Focus-stealing and clipboard-based recovery remain opt-in through `ALLOW_FOCUS_STEAL=False`.
- Clipboard recovery preserves HGLOBAL-backed formats and distinguishes clipboard-open failure from an actually empty clipboard.

## v0.1.10 / v0.1.11 hardening

### Focused-child injection

After the hardened injector posts its deterministic compose click, it asks `GetGUIThreadInfo` for Telegram's focused child HWND. When that HWND belongs to Telegram's process, `WM_CHAR` is posted directly to it. If that route is rejected, the injector falls back to the top-level Telegram HWND.

### Compose-aware audit selection

The audit considers all Edit controls but prefers positive-value controls that geometrically overlap the compose selected for the send. This prevents a pre-filled search field from winning merely because it appears first in the UI Automation tree.

### Delayed-clear verification

A successful Send-button click does not necessarily clear the compose instantly. The hardened injector polls for up to roughly one second before classifying the submission as failed. This reduces false errors and prevents an unnecessary fallback from duplicating a message that was already accepted by Telegram.

### Clipboard write safety

The opt-in clipboard strategy checks the return value from `clipboard_guard.set_text()` before issuing `Ctrl+V`. If Windows refuses the clipboard write, paste recovery is refused rather than risking insertion of unrelated clipboard contents.

### Target lifecycle safety

UIA runtime IDs are treated as session-scoped hints rather than permanent identities. The target tracks the Telegram top-level `(HWND, PID)` scope. When that scope changes, the remembered compose runtime ID is discarded and the compose is rediscovered.

Remembered compose controls are also revalidated for sensible dimensions, lower-window placement, and editability before reuse.

### Safer Send-button geometry

Explicitly named Send controls are preferred when row-aligned. Voice/record/mic/audio controls are rejected. Unnamed candidates are eligible only when they are close to the compose row and at or to the right of the compose field, preventing unrelated lower-window buttons from becoming accidental targets.

### Stale-target send guard

Before every critical compose click, retry, Enter, Send click, and clipboard recovery action, the injector verifies that the original Telegram top-level `(HWND, PID)` still matches the target scope. If Telegram restarts or the window is replaced mid-send, the operation aborts safely rather than continuing against a stale target.

### Per-monitor DPI awareness

`floatingbar/dpi.py` enables Windows per-monitor-V2 DPI awareness before Tk creates its first window, with a legacy Shcore fallback. This keeps Tk/UIA geometry and posted client coordinates more consistent on mixed-DPI and multi-monitor desktops.

### Diagnostics parity

`tools/diagnose.py --send` uses the same `HardenedTelegramInjector` as the production orb. Diagnostic output includes focused HWND, compose click point, runtime IDs, button names, and InvokePattern availability without logging message content.

## Release/deployment

The Windows release workflow checks `floatingbar.__version__`, validates/builds on a Windows runner, creates or repairs the matching version tag only after validation succeeds, and publishes `FloatingBar.exe`. Existing releases are not rebuilt.

Release publishing is serialized by version/repository concurrency. Release notes use an explicit body rather than automatically generated notes so repeated workflow retries cannot duplicate changelog text.

The v0.1.10 deployment incident was traced to a stale tag pointing at an older commit. The workflow was hardened to repair stale tags before publishing, and the corrected v0.1.10 release completed successfully.

## Validation

Windows CI compiles the source tree, executes the unittest suite, and builds the PyInstaller executable. The release workflow performs the same validation before publishing the versioned EXE.

The current development environment cannot execute the final Windows/Telegram UI integration itself. Real desktop validation remains important for Telegram versions, DPI configurations, multiple-monitor layouts, and focus behavior. The trace log intentionally records lengths, geometry, runtime IDs, stages, and booleans — never message content.

## Current regression coverage

The test suite covers nested compose geometry, pre-filled search fields, voice-button rejection, explicit Send selection, ambiguous-button fallback, focused-child routing, delayed compose clearing, clipboard-write failure, stale runtime-ID invalidation, Send-button row filtering, disabled controls, DPI-awareness bootstrap behavior, and stale-target scope aborts.

## Next engineering targets

1. Gather real Windows traces from multiple Telegram versions/builds and compare focused child HWND behavior.
2. Replace remaining Send-button heuristics with an evidence score combining geometry, control patterns, runtime IDs, enabled state, and explicit names.
3. Add an explicit submission evidence model that distinguishes `landed`, `submitted`, `verified`, and `verification-unavailable` without overstating optimistic states.
4. Add regression coverage around repeated sends, emoji/surrogate-pair text, chat switching during a send, minimized Telegram, and Telegram process restart.
5. Generalize the target abstraction to other Windows background apps only after Telegram behavior is stable and well-tested.
