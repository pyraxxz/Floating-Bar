# Floating Bar implementation notes

## Current baseline

The repository evolved from real Telegram traces collected during the earlier implementation work. The production orb uses the hardened injector path, with a dedicated recovery-aware overlay for opt-in fallback strategies.

Established behavior:

- Telegram is located primarily by process image name rather than window title.
- Text injection uses posted `WM_CHAR` UTF-16 code units; UIA `ValuePattern.SetValue` is deliberately not used.
- The compose can expose nested `Edit` controls. The injector audits value lengths and remembers the inner text-holding field for the current Telegram window/process.
- Submission prefers an invisible posted click on Telegram's Send button and falls back to posted Enter combinations when a button cannot be located.
- Minimized Telegram is rejected rather than pretending the send succeeded.
- Focus-stealing and clipboard-based recovery remain opt-in through `ALLOW_FOCUS_STEAL=False`.
- Clipboard recovery preserves HGLOBAL-backed formats and refuses paste if the new clipboard text could not be written safely.

## Telegram targeting hardening

### Focused-child injection

After the hardened injector posts its deterministic compose click, it asks `GetGUIThreadInfo` for Telegram's focused child HWND. When that HWND belongs to Telegram's process, `WM_CHAR` is posted directly to it. If that route is rejected, the injector falls back to the top-level Telegram HWND.

### Compose-aware audit selection

The audit considers all Edit controls but prefers positive-value controls that geometrically overlap the compose selected for the send. This prevents a pre-filled search field from winning merely because it appears first in the UI Automation tree.

### Target lifecycle safety

UIA runtime IDs are session-scoped hints rather than permanent identities. The target tracks the Telegram top-level `(HWND, PID)` scope. When that scope changes, the remembered compose runtime ID is discarded and the compose is rediscovered. Remembered controls are also revalidated for sensible dimensions, lower-window placement, and editability before reuse.

### Stale-target send guard

Before every critical compose click, retry, Enter, Send click, and clipboard-recovery action in the default path, the injector verifies that the original Telegram top-level `(HWND, PID)` still matches the target scope. If Telegram restarts or the window is replaced mid-send, the operation aborts safely rather than continuing against a stale target.

### Multi-window targeting

When the orb opens, it records the top-level window that owned foreground focus. At send time, the target layer re-scans Telegram windows and prefers that exact HWND when it is one of the detected Telegram windows. Otherwise normal discovery remains the fallback. This prevents another Telegram window with a larger rectangle from becoming the accidental destination.

### Safer Send-button evidence

Send candidates now receive a bounded evidence score using explicit accessible name, automation ID, InvokePattern availability, compose-row alignment, position relative to the compose, and reasonable button geometry. Voice/record/mic/audio controls are rejected. Weak unnamed candidates are rejected and posted Enter becomes the fallback.

## Runtime reliability

### Delayed-clear verification

A successful Send-button click does not necessarily clear the compose instantly. The hardened injector polls for up to roughly one second before classifying the submission as failed. This reduces false errors and prevents unnecessary duplicate fallback sends.

### Clipboard write safety

The opt-in clipboard strategy checks the return value from `clipboard_guard.set_text()` before issuing `Ctrl+V`. If Windows refuses the clipboard write, paste recovery is refused rather than risking insertion of unrelated clipboard contents.

### Per-monitor DPI awareness

`floatingbar/dpi.py` enables Windows per-monitor-V2 DPI awareness before Tk creates its first window, with a legacy Shcore fallback. This keeps Tk/UIA geometry and posted client coordinates more consistent on mixed-DPI and multi-monitor desktops.

### Stale worker protection

The UI attaches a monotonic attempt ID to send operations and ignores a result belonging to an older attempt. A delayed worker completion therefore cannot overwrite a newer send's status or retry draft.

### Message fidelity

Message text is not trimmed before injection. Intentional leading and trailing whitespace is preserved, while whitespace-only input is still skipped. UTF-16 conversion retains surrogate pairs for emoji and other astral Unicode.

## Recovery UX

A genuinely failed send keeps the unsent text as a **session-only retry draft**. The next time the orb opens, the draft is restored and selected. Typing a replacement clears the old draft. The draft remains in process memory only.

A send path that completed but could not be reliably confirmed is treated differently from a verified send. The orb flashes amber and shows an explicit warning that the message should be checked before retrying. The unverified message is deliberately not re-offered automatically because it may already exist in Telegram and an automatic retry could duplicate it.

## Submission evidence

Injector strategy strings are mapped into a typed `SubmissionEvidence` model before UI presentation. The model distinguishes `failed`, `submitted`, `verified`, `verification-unavailable`, and `unknown` outcomes, with explicit `confirmed`, `uncertain`, and `retryable` properties. UI policy therefore no longer depends on substring parsing such as treating any strategy containing `verified` as confirmed.

## Opt-in recovery hardening

`floatingbar/recovery.py` provides `ScopeGuardedRecoveryInjector`, which extends the hardened injector only for the optional focus-steal and clipboard-recovery strategies. Before each target interaction it rechecks the original Telegram `(HWND, PID)` scope and raises a hard `InjectionFailed` when the target changes.

`floatingbar/recovery_overlay.py` wires that subclass into the production entry point without modifying the established overlay implementation. This keeps the normal invisible path stable while ensuring the opt-in fallback cannot continue against a replaced Telegram window.

## Diagnostics and tests

`tools/diagnose.py --send` uses the same hardened injector family as the production orb and reports focused HWND, compose click point, runtime IDs, button names, evidence scores, and InvokePattern availability without logging message content.

The regression suite covers nested compose geometry, pre-filled search fields, voice-button rejection, explicit Send selection, ambiguous-button fallback, focused-child routing, delayed compose clearing, clipboard-write failure, stale runtime-ID invalidation, Send-button row filtering, disabled controls, DPI-awareness bootstrap, stale-target scope aborts, multi-window target preference, failed-draft behavior, typed send-state classification, repeated sends, Unicode surrogate-pair handling, and opt-in recovery scope aborts.

## Release/deployment

The Windows release workflow checks `floatingbar.__version__`, validates/builds on Windows, creates or repairs the matching version tag only after validation succeeds, and publishes `FloatingBar.exe`. Existing releases are not rebuilt.

Release publishing is serialized and superseded runs are cancelled. Before building, a queued job checks that `main` has not moved past its own commit; after building, it reconfirms `main` is still at that commit before tagging. This prevents an older queued build from becoming the newest release.

Published EXEs ship with `FloatingBar.exe.sha256`, and the SHA256 is recorded in the release body.

## Validation boundary

Windows CI compiles the source tree, executes the unittest suite, and builds the PyInstaller executable. The release workflow performs the same validation before publishing the versioned EXE.

The development environment cannot execute the final Windows/Telegram UI integration itself. Real desktop validation remains important for Telegram versions, DPI configurations, multiple-monitor layouts, multiple Telegram windows, focus behavior, and Qt accessibility behavior. The trace log intentionally records lengths, geometry, runtime IDs, stages, candidate scores, attempt IDs, and booleans — never message content.

## Current release

**v0.1.19** is the release candidate containing the guarded opt-in recovery path. It should only be considered downloadable after its Windows validation and release publisher both complete successfully.

## Next engineering targets

1. Gather real Windows traces from multiple Telegram versions/builds and compare focused child HWND behavior.
2. Add a safe explicit retry action for genuinely failed drafts while keeping uncertain outcomes non-retriable by default.
3. Improve chat-switch detection so a target selected at orb-open cannot silently become a different conversation before submission.
4. Generalize the target abstraction to other Windows background apps only after Telegram behavior is stable and well-tested.
