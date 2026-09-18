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

## Background application architecture

The production picker is now process-first and title-free. Supported processes resolve through `app_adapters.AppAdapterSpec`, which supplies the user-facing application label, available action, target mode, submission mode, and verification policy. Unknown applications remain discovery-only instead of being treated as safe background targets.

Supported chat adapters expose a short structural conversation picker. Conversation rows are discovered from visible UI Automation `ListItem`/`TreeItem` structure and their accessible names. Message bodies, previews, and input values are never read. The picker keeps the current conversation visible when UIA selection state exposes it. When UI Automation provides a runtime ID, that structural identity is carried through revalidation; name/geometry matching is only a guarded fallback for builds where runtime IDs are unavailable.

Hover navigation deliberately has a transition grace period between the orb, application list, and second-level action popup. The selected background application is also identified in the active bar by adapter label only; window titles and chat content are not surfaced there.

## Chat composer targeting and verification

Chat applications may expose several editable controls, including search/navigation fields. `ChatComposerTarget` therefore prefers structurally composer-shaped `Edit`/`Document` controls when multiple candidates exist. A focused small field does not automatically win over a larger composer-shaped control. The target is still bound to the exact top-level `(HWND, PID)` and the selected input control is pinned and revalidated for each send.

The same target now provides a conservative content-free `compose-clear` verification contract for WhatsApp, Discord, Slack, and Microsoft Teams. Immediately before injection it records only the compose value length. It then requires evidence that the length increased before submission and waits for the same pinned control to return to zero length after submission. Any unavailable/read-error path degrades to `verification-unavailable`; it never upgrades an unknown result to verified. This shared contract is deliberately not claimed as app-specific semantic verification: Slack settings or application-specific editor behavior can leave the composer populated after Enter, in which case the result remains unverified. Even when the composer clears, the final verification step revalidates the pinned control and selected conversation so a race involving window/control reuse or conversation drift cannot publish a false `VERIFIED` result.

## Terminal targeting

Terminal targeting is also structural rather than focus-only. The terminal adapter first accepts an editable control that belongs to the exact bound process; if focus is elsewhere but a structurally discovered console input exists, deterministic candidate scoring selects that control. Pinning uses the same structural inventory and exact process scope. This remains a conservative foundation for multiple Windows Terminal/console-host variants; explicit console-specific submission and verification are still separate work.

## Telegram targeting hardening

### Focused-child injection

After the hardened injector posts its deterministic compose click, it asks `GetGUIThreadInfo` for Telegram's focused child HWND. When that HWND belongs to Telegram's process, `WM_CHAR` is posted directly to it. If that route is rejected, the injector falls back to the top-level Telegram HWND.

### Compose-aware audit selection

The audit considers all Edit controls but prefers positive-value controls that geometrically overlap the compose selected for the send. This prevents a pre-filled search field from winning merely because it appears first in the UI Automation tree.

### Target lifecycle safety

UIA runtime IDs are session-scoped hints, never permanent identities. The target tracks the Telegram top-level `(HWND, PID)` scope. When that scope changes, the remembered compose runtime ID is discarded and the compose is rediscovered. Remembered controls are also revalidated for sensible dimensions, lower-window placement, and editability before reuse.

### Immutable target lease

`BoundTelegramTarget` now turns a preflight-selected Telegram `(HWND, PID)` into an explicit transaction lease. While bound, it refuses a different preferred HWND, refuses to rediscover another Telegram window, and revalidates the original window/process before and after every compose, audit, and Send-button operation. The lease is released when the active UI completion is processed, including completion-handler exceptions; stale worker results cannot release a newer attempt's lease.

### Stale-target send guard

Before every critical compose click, retry, Enter, Send click, and clipboard-recovery action, the injector verifies that the original Telegram top-level `(HWND, PID)` still matches the target scope. If Telegram restarts or the window is replaced mid-send, the operation aborts safely rather than continuing against a stale target.

### Multi-window targeting

When the orb opens, it records the top-level window that owned foreground focus. At send time, the target layer re-scans Telegram windows and prefers that exact HWND when it is one of the detected Telegram windows. Otherwise normal discovery remains the fallback. The production transaction then converts the read-only preflight selection into an immutable lease, so a later rescan cannot silently retarget the send.

### Safer Send-button evidence

Send candidates now use a typed immutable `SendCandidate` carrying the accessible name, client-relative coordinates, and evidence score. The underlying tuple shape remains compatible with the legacy `(name, x, y)` consumers. Evidence combines explicit accessible name, automation ID, InvokePattern availability, compose-row alignment, position relative to the compose, and reasonable button geometry. Voice/record/mic/audio controls are rejected, and unnamed buttons are never clicked merely because their geometry looks convincing.

## Runtime context protection

### Non-content context fingerprint

`floatingbar.context` captures a one-way HMAC fingerprint of a non-generic Telegram window title using a per-process secret. The raw title is never logged or persisted. The fingerprint is used only as a change detector between the read-only preflight and later guarded actions.

### Structural compose anchor

When the chosen compose `Edit` exposes a UI Automation runtime ID, the ID is retained as a session-only structural anchor. It is compared only against the current Edit tree; message content is never read for this purpose. This provides an additional context signal when Telegram uses a generic title and also detects a replaced compose control after preflight.

### Preflight drift check

Preflight captures a non-content title snapshot before compose/button discovery and compares it with the final context snapshot. A context/title transition during the preflight itself is treated conservatively as a blocked send when at least one snapshot has usable title evidence. When no usable context anchor exists, the result explicitly reports degraded protection rather than falsely claiming stability.

The combination is intentionally not an assertion of exact chat identity for every Telegram build. Same-window chat switches can remain indistinguishable when Telegram reuses both the same generic title and the same structural compose control. The application must degrade safely and report the boundary rather than infer content.

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

### Authoritative transaction lifecycle

The transaction lifecycle now owns evidence-to-terminal-state mapping. Production completion handling passes the typed `EvidenceState` into `TransactionLifecycle.complete_from_evidence()` rather than duplicating that policy in the UI layer. This keeps verified, uncertain, and failed outcomes aligned with one state machine and gives regression tests one place to enforce the safety contract.

## Recovery UX

A genuinely failed send keeps the unsent text as a **session-only retry draft**. The next time the orb opens, the draft is restored and selected. Typing a replacement clears the old draft. The draft remains in process memory only.

A send path that completed but could not be reliably confirmed is treated differently from a verified send. The orb flashes amber and shows an explicit warning that the message should be checked before retrying. The unverified message is deliberately not re-offered automatically because it may already exist in Telegram and an automatic retry could duplicate it.

### Explicit retry action

A genuinely failed draft can be restored through the existing right-click menu using **Retry failed draft**. The action preserves the original Telegram target before refocusing the orb, restores/selects the draft, and never submits automatically. Typing a replacement clears the saved retry context. This makes retry deliberate rather than implicit.

## Submission evidence

Injector strategy strings are mapped into a typed `SubmissionEvidence` model before UI presentation. The model distinguishes `failed`, `submitted`, `verified`, `verification-unavailable`, and `unknown` outcomes, with explicit `confirmed`, `uncertain`, and `retryable` properties. UI policy therefore no longer depends on substring parsing such as treating any strategy containing `verified` as confirmed.

The transaction layer also carries typed immutable `SendCompletion` objects for future coordinator work. A completion is considered failed from either an explicit error or an explicit `EvidenceState.FAILED`, independent of its diagnostic strategy string.

## Opt-in recovery hardening

`floatingbar/recovery.py` provides `ScopeGuardedRecoveryInjector`, which extends the hardened injector only for the optional focus-steal and clipboard-recovery strategies. Before each target interaction it rechecks the original Telegram `(HWND, PID)` scope and raises a hard `InjectionFailed` when the target changes.

`floatingbar/recovery_overlay.py` wires that subclass into the production entry point without modifying the established overlay implementation. This keeps the normal invisible path stable while ensuring the opt-in fallback cannot continue against a replaced Telegram window.

## Diagnostics and safe preflight

`tools/diagnose.py` remains read-only by default and reports focused HWND, compose click point, runtime IDs, button names, evidence scores, and InvokePattern availability without logging message content.

`tools/diagnose.py --preflight` runs a dedicated non-invasive readiness check. It verifies that Telegram exists, is not minimized, has usable compose geometry, and retains a stable `(HWND, PID)` target during discovery. It returns the one captured non-content `WindowContext` snapshot used by production for the send attempt; generic Telegram titles deliberately produce degraded context protection rather than a false claim of chat identity.

`tools/diagnose.py --preflight --json` emits a machine-readable, content-free representation containing readiness/status, target and focus identifiers, compose geometry, submission path, Send evidence score, context-guard booleans, and safe reasons. It deliberately omits Telegram raw titles, message text, and clipboard contents.

`tools/diagnose.py --send` now follows the production transaction boundary: it runs read-only preflight, binds the exact resulting target through `BoundTelegramTarget`, adopts the preflight context snapshot, sends through `ContextGuardedRecoveryInjector`, and always releases the temporary target lease.

The regression suite covers nested compose geometry, pre-filled search fields, voice-button rejection, explicit Send selection, ambiguous-button fallback, focused-child routing, delayed compose clearing, clipboard-write failure, stale runtime-ID invalidation, immutable target leases, preflight context replacement, preflight context drift, Send-button row filtering, disabled controls, DPI-awareness bootstrap, stale-target scope aborts, multi-window target preference, failed-draft behavior, typed send-state classification, typed Send candidates, repeated sends, Unicode surrogate-pair handling, opt-in recovery scope aborts, explicit retry-menu behavior, production lease lifecycle, structural context anchors, machine-readable diagnostic payloads, safe-preflight readiness states, authoritative transaction/evidence lifecycle mapping, and the shared compose-clear contract across WhatsApp, Discord, Slack, and Teams.

## Release/deployment

The project now follows **milestone-based releases**. Ordinary pushes to `main` run Windows CI but do not publish a release. The release workflow only runs for an explicit `vMAJOR.MINOR.PATCH` tag or an intentional manual publish of an existing version tag.

Release publishing is serialized and superseded runs are cancelled. A release build validates the exact tag source, checks that the package version matches the tag, runs the complete Windows regression suite, builds the PyInstaller executable, confirms the tag did not move during the build, calculates SHA-256, then publishes `FloatingBar.exe` and `FloatingBar.exe.sha256`.

Published releases are not rebuilt automatically. This keeps downloadable artifacts tied to intentional milestones rather than every small improvement pushed to `main`.

The development CI workflow is also concurrency-limited per branch/ref and cancels superseded runs. A rapid implementation burst therefore keeps only the newest Windows validation run instead of creating a backlog of stale runs and duplicate failure notifications.

The CI workflows use current Node 24-compatible GitHub Actions lines: `actions/checkout@v6`, `actions/setup-python@v7`, `actions/github-script@v9`, `softprops/action-gh-release@v3`, and `actions/upload-artifact@v4`.

## Validation boundary

Windows CI compiles the source tree, executes the unittest suite, and builds the PyInstaller executable. The release workflow performs the same validation before publishing the versioned EXE.

The development environment cannot execute the final Windows/Telegram UI integration itself. Real desktop validation remains important for Telegram versions, DPI configurations, multiple-monitor layouts, multiple Telegram windows, restart, minimized state, focus behavior, Qt accessibility behavior, and the actual meaning of Telegram's current UIA tree. The trace log intentionally records lengths, geometry, runtime IDs, stages, candidate scores, attempt IDs, and booleans — never message content.

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
4. Add conservative terminal verification/retry semantics only when a non-content terminal signal can distinguish accepted input from mere key delivery.
5. Generalize the target abstraction to other Windows background apps only after Telegram behavior is stable and well-tested.


## Lightweight settings and startup behavior

The orb now exposes a small Settings dialog instead of requiring users to edit configuration constants manually. It persists only the idle-collapse preference in a bounded JSON file and manages Windows startup through the current user's Run key. The packaged executable is registered directly; source launches register the Python interpreter plus the current script. No background-app identity or UI content enters the settings store.


## Packaging and clean upgrade path

The repository now ships non-elevated PowerShell installer and uninstaller scripts alongside the PyInstaller executable. Upgrades replace only the installed executable, refuse to overwrite a running copy, and preserve %APPDATA%/FloatingBar settings and quick replies. The uninstaller removes the executable and Start-menu shortcut while preserving user data unless -RemoveSettings is explicitly supplied. CI parses both scripts before the Python regression gate, and release builds publish the scripts with the executable.

The installer copies the bundled uninstaller into the install directory when available, keeping the installed copy self-contained for later removal.


## Release update notification

The orb menu now exposes an explicit update check. It queries only the public latest-release metadata for the GitHub repository, uses a bounded network timeout, never checks on startup, and runs off the Tk UI thread. A newer release opens a small local dialog with an explicit release-page action; a failed check exposes only a generic UI state while the detailed exception remains content-free in trace diagnostics.


## Multi-monitor/DPI validation evidence

The Windows validation snapshot now records bounded per-monitor geometry and effective DPI alongside the process DPI-awareness mode. It intentionally omits display-device names and any UI content, making mixed-DPI and multi-monitor acceptance reports more reproducible without adding machine-identifying display metadata.


## Smoke-report environment integrity

The release-gate validator now cross-checks critical PASS cases against the report's content-free environment snapshot. Mixed-DPI PASS requires at least two monitors with distinct effective DPI values, and critical Telegram/terminal acceptance PASS cases require the matching supported process family to have been observed in that same snapshot. This prevents a completed report from silently mixing manual results with unrelated environment evidence.


## Configurable summon hotkey

The Settings dialog now persists one of four predefined global summon shortcuts. The choice is normalized against a fixed allowlist and loaded before hotkey registration at startup. Changing it intentionally requires an application restart so the current global registration is never torn down or replaced unexpectedly while the app is in use.


## Content-free conversation identity hardening

Conversation runtime IDs and structural control/container identities are now authoritative for picker, recent-target, and pinned-target identity. Visible conversation names remain display labels and are only used as an identity fallback when no stronger UI identity is available. Strongly identified rows may therefore be renamed or relabeled without becoming a new target, while runtime/control/container drift continues to fail closed.
