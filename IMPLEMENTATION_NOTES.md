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

Supported chat adapters currently expose a short structural conversation picker. Conversation rows are discovered from visible UI Automation `ListItem`/`TreeItem` structure and their accessible names. Message bodies, previews, and input values are never read. The picker keeps the current conversation visible when UIA selection state exposes it. When UI Automation provides a runtime ID, that structural identity is carried through revalidation; name/geometry matching is only a guarded fallback for builds where runtime IDs are unavailable.

Hover navigation deliberately has a transition grace period between the orb, application list, and second-level action popup. The selected background application is also identified in the active bar by adapter label only; window titles and chat content are not surfaced there.

## Chat composer targeting

Chat applications may expose several editable controls, including search/navigation fields. `ChatComposerTarget` therefore prefers structurally composer-shaped `Edit`/`Document` controls when multiple candidates exist. A focused small field does not automatically win over a larger composer-shaped control. The target is still bound to the exact top-level `(HWND, PID)` and the selected input control is pinned and revalidated for each send.

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
