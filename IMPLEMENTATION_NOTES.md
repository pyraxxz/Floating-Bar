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

UIA runtime IDs are session-scoped hints, never permanent identities. The target tracks the Telegram top-level `(HWND, PID)` scope. When that scope changes, the remembered compose runtime ID is discarded and the compose is rediscovered. Remembered controls are also revalidated for sensible dimensions, lower-window placement, and editability before reuse.

### Stale-target send guard

Before every critical compose click, retry, Enter, Send click, and clipboard-recovery action, the injector verifies that the original Telegram top-level `(HWND, PID)` still matches the target scope. If Telegram restarts or the window is replaced mid-send, the operation aborts safely rather than continuing against a stale target.

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

### Explicit retry action

A genuinely failed draft can be restored through the existing right-click menu using **Retry failed draft**. The action preserves the original Telegram target before refocusing the orb, restores/selects the draft, and never submits automatically. The command is disabled for verified, uncertain, and idle states. This makes retry deliberate rather than implicit.

## Submission evidence

Injector strategy strings are mapped into a typed `SubmissionEvidence` model before UI presentation. The model distinguishes `failed`, `submitted`, `verified`, `verification-unavailable`, and `unknown` outcomes, with explicit `confirmed`, `uncertain`, and `retryable` properties. UI policy therefore no longer depends on substring parsing such as treating any strategy containing `verified` as confirmed.

## Opt-in recovery hardening

`floatingbar/recovery.py` provides `ScopeGuardedRecoveryInjector`, which extends the hardened injector only for the optional focus-steal and clipboard-recovery strategies. Before each target interaction it rechecks the original Telegram `(HWND, PID)` scope and raises a hard `InjectionFailed` when the target changes.

`floatingbar/recovery_overlay.py` wires that subclass into the production entry point without modifying the established overlay implementation. This keeps the normal invisible path stable while ensuring the opt-in fallback cannot continue against a replaced Telegram window.

## Diagnostics and safe preflight

`tools/diagnose.py` remains read-only by default and reports focused HWND, compose click point, runtime IDs, button names, evidence scores, and InvokePattern availability without logging message content.

`tools/diagnose.py --preflight` runs a dedicated non-invasive readiness check. It verifies that Telegram exists, is not minimized, has usable compose geometry, and retains a stable `(HWND, PID)` target during discovery. It reports whether a safe Send-button candidate exists; lack of a button is a warning rather than a hard failure because the production cascade has an Enter fallback.

`tools/diagnose.py --send` uses the same hardened injector family as the production orb and preserves the foreground Telegram target when one was selected before the command started.

The regression suite covers nested compose geometry, pre-filled search fields, voice-button rejection, explicit Send selection, ambiguous-button fallback, focused-child routing, delayed compose clearing, clipboard-write failure, stale runtime-ID invalidation, Send-button row filtering, disabled controls, DPI-awareness bootstrap, stale-target scope aborts, multi-window target preference, failed-draft behavior, typed send-state classification, repeated sends, Unicode surrogate-pair handling, opt-in recovery scope aborts, explicit retry-menu behavior, and safe-preflight readiness states.

## Release/deployment

The project now follows **milestone-based releases**. Ordinary pushes to `main` run Windows CI but do not publish a release. The release workflow only runs for an explicit `vMAJOR.MINOR.PATCH` tag or an intentional manual publish of an existing version tag.

Release publishing is serialized and superseded runs are cancelled. A release build validates the exact tag source, checks that the package version matches the tag, runs the complete Windows regression suite, builds the PyInstaller executable, confirms the tag did not move during the build, calculates SHA-256, then publishes `FloatingBar.exe` and `FloatingBar.exe.sha256`.

Published releases are not rebuilt automatically. This keeps downloadable artifacts tied to intentional milestones rather than every small improvement pushed to `main`.

The CI workflows use current Node 24-compatible GitHub Actions lines: `actions/checkout@v6`, `actions/setup-python@v7`, `actions/github-script@v9`, `softprops/action-gh-release@v3`, and `actions/upload-artifact@v4`.

## Validation boundary

Windows CI compiles the source tree, executes the unittest suite, and builds the PyInstaller executable. The release workflow performs the same validation before publishing the versioned EXE.

The development environment cannot execute the final Windows/Telegram UI integration itself. Real desktop validation remains important for Telegram versions, DPI configurations, multiple-monitor layouts, multiple Telegram windows, focus behavior, Qt accessibility behavior, and the actual meaning of Telegram's current UIA tree. The trace log intentionally records lengths, geometry, runtime IDs, stages, candidate scores, attempt IDs, and booleans — never message content.

## Current release and milestone policy

**v0.1.20** is the current published stable release and remains the downloadable baseline. The ongoing `main` line is intentionally allowed to move ahead of the release while development continues.

A new release should be cut only when we reach a meaningful product milestone such as:

1. a demonstrably more reliable Telegram send transaction across real-world window/process states;
2. a substantial user-facing capability that changes the core workflow; or
3. a coherent production-readiness milestone backed by Windows validation and real desktop smoke testing.

Patch-level fixes, refactors, tests, diagnostics, and small reliability improvements should normally accumulate on `main` without creating a new public release.

## Next engineering targets

1. Improve chat-switch detection without reading or logging Telegram message content.
2. Build a practical Windows/Telegram desktop smoke-test checklist covering DPI, multiple monitors, multiple Telegram windows, restart, minimized state, and repeated sends.
3. Use real-world traces from multiple Telegram builds to tune focused-child and Send-button evidence rather than guessing from one UIA tree.
4. Generalize the target abstraction to other Windows background apps only after Telegram behavior is stable and well-tested.
