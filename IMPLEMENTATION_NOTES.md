# Floating Bar implementation notes

## Current baseline

The repository evolved from real Telegram traces collected during the earlier implementation work. The production orb uses the hardened injector path rather than the original injector directly.

Established behavior:

- Telegram is located primarily by process image name rather than window title.
- Text injection uses posted `WM_CHAR` UTF-16 code units; UIA `ValuePattern.SetValue` is deliberately not used.
- The compose can expose nested `Edit` controls. The injector audits value lengths and remembers the inner text-holding field for the current Telegram window/process.
- Submission prefers an invisible posted click on Telegram's Send button and falls back to posted Enter combinations when a button cannot be located.
- Minimized Telegram is rejected rather than pretending the send succeeded.
- Focus-stealing and clipboard-based recovery remain opt-in through `ALLOW_FOCUS_STEAL=False`.
- Clipboard recovery preserves HGLOBAL-backed formats and distinguishes clipboard-open failure from an actually empty clipboard.

## Telegram targeting hardening

### Focused-child injection

After the hardened injector posts its deterministic compose click, it asks `GetGUIThreadInfo` for Telegram's focused child HWND. When that HWND belongs to Telegram's process, `WM_CHAR` is posted directly to it. If that route is rejected, the injector falls back to the top-level Telegram HWND.

### Compose-aware audit selection

The audit considers all Edit controls but prefers positive-value controls that geometrically overlap the compose selected for the send. This prevents a pre-filled search field from winning merely because it appears first in the UI Automation tree.

### Target lifecycle safety

UIA runtime IDs are session-scoped hints rather than permanent identities. The target tracks the Telegram top-level `(HWND, PID)` scope. When that scope changes, the remembered compose runtime ID is discarded and the compose is rediscovered. Remembered controls are also revalidated for sensible dimensions, lower-window placement, and editability before reuse.

### Stale-target send guard

Before every critical compose click, retry, Enter, Send click, and clipboard recovery action, the injector verifies that the original Telegram top-level `(HWND, PID)` still matches the target scope. If Telegram restarts or the window is replaced mid-send, the operation aborts safely rather than continuing against a stale target.

### Multi-window targeting

When the orb opens, it records the top-level window that owned foreground focus. At send time, the target layer re-scans Telegram windows and prefers that exact HWND when it is one of the detected Telegram windows. Otherwise normal discovery remains the fallback. This prevents another Telegram window with a larger rectangle from becoming the accidental destination.

### Safer Send-button geometry

Explicitly named Send controls are preferred when row-aligned. Voice/record/mic/audio controls are rejected. Unnamed candidates are eligible only when they are close to the compose row and at or to the right of the compose field, preventing unrelated lower-window buttons from becoming accidental targets.

## Runtime reliability

### Delayed-clear verification

A successful Send-button click does not necessarily clear the compose instantly. The hardened injector polls for up to roughly one second before classifying the submission as failed. This reduces false errors and prevents unnecessary duplicate fallback sends.

### Clipboard write safety

The opt-in clipboard strategy checks the return value from `clipboard_guard.set_text()` before issuing `Ctrl+V`. If Windows refuses the clipboard write, paste recovery is refused rather than risking insertion of unrelated clipboard contents.

### Per-monitor DPI awareness

`floatingbar/dpi.py` enables Windows per-monitor-V2 DPI awareness before Tk creates its first window, with a legacy Shcore fallback. This keeps Tk/UIA geometry and posted client coordinates more consistent on mixed-DPI and multi-monitor desktops.

## v0.1.14 recovery UX

A genuinely failed send keeps the unsent text as a **session-only retry draft**. The next time the orb opens, the draft is restored and selected. Typing a replacement clears the old draft. The draft remains in process memory only.

A send path that completed but could not be reliably confirmed is treated differently from a verified send. The orb flashes amber and shows an explicit warning that the message should be checked before retrying. The unverified message is deliberately not re-offered automatically because it may already exist in Telegram and an automatic retry could duplicate it.

The UI classifies injector results into `failed`, `unverified`, `verified`, or `unknown` states. This keeps presentation policy separate from strategy names.

## Diagnostics and tests

`tools/diagnose.py --send` uses the same `HardenedTelegramInjector` as the production orb. Diagnostic output includes focused HWND, compose click point, runtime IDs, button names, and InvokePattern availability without logging message content.

The regression suite covers nested compose geometry, pre-filled search fields, voice-button rejection, explicit Send selection, ambiguous-button fallback, focused-child routing, delayed compose clearing, clipboard-write failure, stale runtime-ID invalidation, Send-button row filtering, disabled controls, DPI-awareness bootstrap, stale-target scope aborts, multi-window target preference, and send-state classification.

## Release/deployment

The Windows release workflow checks `floatingbar.__version__`, validates/builds on Windows, creates or repairs the matching version tag only after validation succeeds, and publishes `FloatingBar.exe`. Existing releases are not rebuilt.

Release publishing is serialized by repository/ref concurrency. Before building, a queued job checks that `main` has not moved past its own commit; after building, it reconfirms `main` is still at that commit before tagging. This prevents an older queued build from becoming the newest release.

Published EXEs ship with `FloatingBar.exe.sha256`, and the SHA256 is recorded in the release body.

The v0.1.10 deployment incident was traced to a stale tag and a release API failure. The workflow was hardened to repair stale tags before publication and to keep validation ahead of release tagging. Releases v0.1.11 through v0.1.14 have since completed their Windows validation/build/release paths successfully.

## Validation boundary

Windows CI compiles the source tree, executes the unittest suite, and builds the PyInstaller executable. The release workflow performs the same validation before publishing the versioned EXE.

The development environment cannot execute the final Windows/Telegram UI integration itself. Real desktop validation remains important for Telegram versions, DPI configurations, multiple-monitor layouts, multiple Telegram windows, focus behavior, and Qt accessibility behavior. The trace log intentionally records lengths, geometry, runtime IDs, stages, and booleans — never message content.

## Next engineering targets

1. Build an explicit submission-evidence model (`landed`, `submitted`, `verified`, `verification-unavailable`) and propagate it through the UI without relying on strategy-string parsing.
2. Replace remaining Send-button heuristics with an evidence score combining geometry, control patterns, runtime IDs, enabled state, and explicit names.
3. Add regression coverage around repeated sends, emoji/surrogate-pair text, chat switching during a send, minimized Telegram, and Telegram process restart.
4. Add a safe retry action for failed drafts while keeping unverified results non-retriable by default.
5. Generalize the target abstraction to other Windows background apps only after Telegram behavior is stable and well-tested.
