# Floating Bar

A tiny, always-on-top translucent orb for Windows that is evolving into a background-input layer: choose an already-open application, target a safe input control or conversation, type, submit, and verify without bringing the target application to the foreground.

The original product started as a Telegram Desktop one-way injector. The current `main` development build keeps that hardened Telegram path while adding structural background typing for Terminal, WhatsApp, Discord, Slack, Microsoft Teams, and unknown typeable executables.

No background-app message content is scraped into logs or history. Target discovery uses process/window identity and UI Automation structure, with exact HWND/PID and control revalidation before background sends.

---

## Current development build

Hover the orb to see open background applications. The picker can expose a second-level action such as **Type** or **Chats** without foregrounding the selected application.

The current implementation includes:

* content-free background application discovery, including minimized windows;
* Telegram chat selection with structural/runtime identity checks and unread-badge attention detection;
* generic structural typing for unknown `.exe` applications;
* dedicated structural targets for terminal and chat-composer applications;
* session-only **Recent** applications/conversations with exact HWND/PID revalidation;
* persistent **Pinned** application/conversation targets using only stable adapter/process/label identity;
* persistent user-authored **Quick replies** that insert a draft but never auto-send it;
* a global `Ctrl+Alt+Space` summon hotkey;
* a lightweight Settings dialog for Windows startup and idle-collapse behavior;
* a first-run mini-tutorial and content-free background-target feedback;
* machine-readable Windows smoke-test tooling and a 33-case declarative desktop smoke matrix.

Pins and quick replies are intentionally separate from background-app discovery: no HWND/PID/runtime identifiers are persisted for pins, and quick-reply text is stored only because the user explicitly saved it.

The Windows CI gate currently runs for pull requests (plus manual dispatch), compiles the Python sources, runs the regression suite, and builds the Windows executable with PyInstaller before a change is merged.

---

## Requirements

* Windows 10 or 11
* Python 3.9+ (with Tk — the standard python.org installer includes it)
* Run Floating Bar unelevated as a normal user-level app.
* Windows UIPI rules mean a normal Floating Bar process cannot inject into an elevated target process.

Telegram-specific development validation still requires **Telegram Desktop running with a chat open**. Other supported adapters require their corresponding desktop application to be open and expose a structurally discoverable input control.

## Setup

```bat
pip install -r requirements.txt
python main.py
```

A second launch exits silently (single-instance).

### Just want the exe? (no Python, no command line)

The stable downloadable milestone is published as a GitHub Release with
**FloatingBar.exe** plus a SHA-256 checksum file. New releases are created
only for meaningful milestones; ordinary development commits on `main` do
not publish a new version.

https://github.com/pyraxxz/Floating-Bar/releases

Current stable release: **v0.1.20**.

Prefer building it yourself? Right-click `build.ps1` → *Run with
PowerShell* (or run the equivalent manually):

```bat
pip install pyinstaller
pyinstaller --onefile --noconsole --name FloatingBar main.py
```

The local build also copies installer/Install-FloatingBar.ps1 and installer/Uninstall-FloatingBar.ps1 into dist. The installer places the executable under %LOCALAPPDATA%\\FloatingBar and preserves the existing %APPDATA%\\FloatingBar settings and quick replies during upgrades.

---

## Background-target flow

The intended interaction is:

`orb → background app → Type/Chats → target → safe structural probe → type → submit → typed evidence`

The picker never needs the target application's window title to identify an app. Duplicate windows use deterministic app ordinals such as `Microsoft Teams 1` and `Microsoft Teams 2`.

Known chat adapters open a conversation picker. The picker can show proven attention state, recent rows, and persistent pins while revalidating the actual live HWND/PID and structural row identity before using a target.

Unknown `.exe` applications receive a conservative generic **Type** action. The action is only usable when the generic structural target can discover a suitable editable control; unsupported or ambiguous controls fail closed rather than falling back to blind focused-input injection.

---

## Recent and pinned targets

**Recent** targets exist only for the current Floating Bar session. They record enough structural identity to offer a useful target again, then revalidate the exact window/process before showing or using it.

**Pinned** targets persist across restarts, but only stable identity is stored: adapter key, executable name, and safe application/conversation label. Live HWND/PID/runtime IDs are never restored from disk; the application resolves and validates a fresh target every time.

When a pin is ambiguous — for example, more than one live window matches the same executable identity — it is suppressed instead of guessing.

## Quick replies

Quick replies are explicitly user-authored local snippets. From the orb's right-click menu, choose **Quick replies** to insert a saved reply into the active input bar, or choose **Manage quick replies** to create, edit, use, or delete entries.

Using a quick reply only inserts it as a draft. **Enter is still required to send it.** The quick-reply store is bounded and uses atomic file replacement so a partial write does not replace the previous valid file.

Quick replies are intentionally different from background-app privacy: the app never copies message content from Telegram, WhatsApp, Discord, Slack, Teams, or another background app into the quick-reply store. Only text that the user explicitly saves as a quick reply is persisted.

---

## How Telegram sending works

Telegram remains the most deeply hardened adapter. Sending is designed to avoid bringing Telegram to the foreground. The production path is a guarded cascade:

1. Capture the window that owned focus when the orb was opened.
2. Locate Telegram by process image name. If the captured foreground HWND is a Telegram window, prefer that exact window; otherwise fall back to normal Telegram discovery.
3. Capture the Telegram top-level `(HWND, PID)` scope for the send.
4. When Telegram was the active window, capture a per-process HMAC fingerprint of its window title so a conversation switch can be detected without retaining the title itself. Generic `Telegram`/`Telegram Desktop` titles are intentionally treated as unavailable context.
5. Run a read-only safe-send preflight. It can block unsafe targets before any click, keypress, or clipboard mutation. A missing Send button is not itself fatal because posted Enter remains a valid fallback.
6. Post an invisible click into the chosen compose field.
7. Ask Windows which child HWND currently owns focus and, when it belongs to Telegram, post UTF-16 `WM_CHAR` units directly to that child. Fall back to the top-level Telegram window only when necessary.
8. Audit Edit controls using **value lengths only**. If another Edit is already non-empty (for example, the search field), prefer the positive-value Edit that geometrically overlaps the selected compose.
9. Remember the confirmed inner compose runtime ID only for the current Telegram window/process. After Telegram restarts, or when the remembered control no longer has valid lower-window compose geometry, the cache is discarded and the compose is rediscovered.
10. Before every critical click/keypress, verify that the same Telegram top-level HWND/PID is still the target. A restart or window replacement aborts the current send safely instead of risking delivery into a changed target.
11. When the compose is verifiably holding the text, submit through a scored Send-button/Enter cascade with strict voice/mic rejection. Candidate evidence combines explicit `Send` naming, automation IDs, InvokePattern availability, compose-row alignment, position relative to the compose, and reasonable button geometry.
12. Submission verification is bounded and asynchronous: a send click is allowed time to clear the compose before it is classified as a failure, reducing false failures and avoiding unnecessary duplicate fallback sends.
13. When the landing cannot be verified, only an explicitly named `Send` button can be clicked. Ambiguous controls are rejected; posted Enter combinations are the fallback.
14. The injector result is converted into typed submission evidence before UI presentation. The UI does not infer confirmation by parsing strategy-name substrings.
15. Text is converted into UTF-16LE code units before posting `WM_CHAR`, preserving surrogate pairs for emoji and other astral Unicode characters.
16. Each UI send attempt carries a monotonic attempt ID. A result from an older worker is ignored if a newer attempt is already active.
17. Message text is not trimmed before injection. Intentional leading or trailing whitespace is preserved; only whitespace-only submissions are skipped.
18. The optional focus-stealing/clipboard recovery path is guarded by the same target checks and never runs unless explicitly enabled in config.

### Failure recovery and retry

A genuinely failed send keeps the unsent text as a **session-only retry draft**. The next time you open the orb, the draft is restored and selected so you can replace it or send it again.

There is also an explicit **Retry failed draft** command in the right-click menu. It is enabled only after a genuinely failed, retryable send. Selecting it restores the draft and focuses the input, but **does not send anything automatically**.

A path that completes without reliable read-back confirmation is deliberately **amber**, not green, and is never offered as an automatic retry because the message may already exist in the target application.

---

## Safe preflight diagnostics

Before testing a live Telegram send, run the read-only preflight:

```bat
python tools/diagnose.py --preflight
```

The preflight never clicks, types, changes foreground focus, reads message content, or touches the clipboard.

For the complete real-desktop validation sequence, see
[`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md).

The Windows environment snapshot and smoke-report tools are also available:

```bat
python tools/validate_windows.py
python tools/smoke_report.py --init smoke-report.json
python tools/smoke_report.py --validate smoke-report.json
```

These commands describe environment readiness and test-report state; they do not claim that the real desktop smoke matrix has passed until actual Windows results are recorded.

---

## The orb's status colors

| Color | Meaning |
|---|---|
| blue | a supported background target is available |
| gray | no supported target is currently bound |
| amber pulse | injection in flight |
| amber flash | the send path completed but could not be confirmed |
| green flash | sent and verified |
| red flash | failed; the draft is preserved for retry |

---

## The right-click menu (and how to quit)

There's no taskbar entry, so the orb has a right-click menu. It shows the version you're running, opens the trace folder, provides **Retry failed draft** when a failed draft exists, exposes **Quick replies**, provides **Manage quick replies**, and has **Quit** — the normal way to close the app.

## The trace log — what to send when something misbehaves

Every send attempt writes a stage-by-stage trace (strategy labels,
pattern availability, verification results, focused-HWND decisions,
target-scope decisions, candidate evidence scores, attempt IDs —
**never message content**) to:

```text
%APPDATA%\FloatingBar\trace.log
```

Right-click the orb → **Open trace folder**, and share the log after a
failed send.

## Diagnostics

A read-only diagnostic for the Telegram adapter is:

```bat
python tools/diagnose.py
```

A live end-to-end Telegram test uses the same context-aware, scope-guarded injector family as the app:

```bat
python tools/diagnose.py --send "test 123"
```

---

## Troubleshooting

* **A solid dark box instead of transparency** — your Tk build mishandles
  `-alpha` combined with `-transparentcolor`. Set `USE_WINDOW_ALPHA = False`
  in `config.py`; the color-key alone keeps working.
* **A background app is listed but cannot be used** — the process is known,
  but structural input discovery did not find a safe editable control. The
  fail-closed behavior is intentional.
* **A recent or pinned target disappeared** — its exact window/process or
  structural conversation identity could not be revalidated. Re-select the
  live app rather than reusing a stale target.
* **A pin is missing while multiple windows are open** — persistent pins
  intentionally refuse ambiguous process matches.
* **A quick reply does not send** — that is intentional. Selecting a quick
  reply only inserts a draft; press Enter to submit it.
* **Text never arrives in Telegram** — run `tools/diagnose.py --preflight`.
* **Multiple Telegram windows** — when the orb was opened while Telegram
  itself was active, the selected Telegram window is preserved. When the orb
  was opened from another application, normal Telegram discovery is used.
* **Send could not be confirmed** — do not immediately retry unless you have
  checked the target chat. Uncertain outcomes are deliberately amber to avoid
  duplicate sends.
* **A previous send failed** — right-click the orb and choose **Retry failed
  draft**, or open the orb normally to recover the selected draft.
* **The orb is blue but sending fails** — most likely UIPI: don't run
  Floating Bar (or the target application) elevated while the other runs
  normally.
* **Mixed-DPI/multi-monitor setup** — per-monitor DPI awareness is enabled
  before the UI is created. Restart the app after changing Windows display
  scaling.
* **A target application restarts during a send** — the exact HWND/PID scope
  check should abort safely rather than continuing into a replacement process.
* **Unicode/emoji appears corrupted** — the Telegram injector posts UTF-16LE
  code units, including surrogate pairs for astral Unicode. The generic
  adapters use their structural target's configured text path.
* **A delayed result appears to affect a newer send** — worker results carry
  attempt IDs and stale completions are ignored.
* **Leading/trailing spaces disappear** — intentional whitespace is preserved.
  Only whitespace-only submissions are skipped.
* **Telegram must not be minimized for the legacy Telegram coordinate-click
  path.** Background (behind other windows) is supported.

## Privacy

Background-app message content is not scraped into the picker, recent-target
store, pins, traces, or diagnostics. Target discovery uses process identity,
window identity, UI Automation roles/classes/pattern availability, geometry,
and other structural signals.

For Telegram conversation-switch protection, the window title is reduced to a
**per-process HMAC-SHA256 fingerprint** held only for the current send context.
The raw title and random HMAC key are not logged, persisted, or exposed.
Generic Telegram titles are not fingerprinted.

Persistent pins store only adapter key, executable name, and safe application
or conversation label. They do **not** store HWND/PID/runtime identifiers or
message content.

Quick replies are the intentional exception to “nothing is persisted”: the
user explicitly chooses their own quick-reply labels and text, and those
entries are stored locally so they survive restarts. The app never populates
quick replies from messages found in background applications.

No telemetry. No network. No Telegram credentials.

## Release integrity

Release builds are validated on Windows before publication. Public releases
are **milestone-only**: ordinary pushes to `main` do not publish a new version.
A release must be created intentionally from a `vMAJOR.MINOR.PATCH` tag or an
explicit manual publish of an existing tag. The publisher validates that exact
tag before building, calculates the EXE checksum, and publishes
`FloatingBar.exe` plus `FloatingBar.exe.sha256`.

## Limitations and remaining validation work

The implementation is ahead of the currently downloadable Telegram-only
stable release. The following still require real desktop validation before a
new public milestone can claim broad app support:

* Windows 10 and Windows 11 desktop smoke tests;
* mixed-DPI and multi-monitor coverage;
* minimized/background and multiple-window tests for each supported app;
* app restart/process replacement tests;
* Unicode/emoji/long-text and repeated-send tests;
* traces from multiple Telegram Desktop builds;
* final app-specific verification/submit semantics where shared structural
  evidence is insufficient;
* installer/startup, signed packaging, clean upgrade, and release-update work.

## Release policy

**v0.1.20** is the current stable downloadable milestone. Development now
continues on `main` without public version bumps for individual fixes.
The next public release will be cut only after a meaningful milestone is
complete and the accumulated Windows regression suite plus the applicable
real-desktop smoke tests pass.
