# Floating Bar

A tiny, always-on-top, fully translucent orb for Windows.

Click the orb → a transparent input bar appears in its place → type → hit
Enter → the text lands in **whatever chat is currently open in Telegram
Desktop**. The bar collapses back to the dot. That's the whole product.

No login. No Telegram API, account access, or credentials. No message
history, no chat display, no read receipts. This is a **one-way blind
injector** — it never reads Telegram's content back.

---

## Requirements

* Windows 10 or 11
* Python 3.9+ (with Tk — the standard python.org installer includes it)
* **Telegram Desktop running with a chat open** (unelevated, same as Telegram)
* Run Floating Bar **unelevated** — a normal user-level app. Windows'
  UIPI rules block input injection between different integrity levels, so
  running it as admin would make it *less* able to reach Telegram.

## Setup

```bat
pip install -r requirements.txt
python main.py
```

A second launch exits silently (single-instance).

### Just want the exe? (no Python, no command line)

Each unreleased package version on `main` is automatically validated on
Windows and published as a GitHub Release with **FloatingBar.exe** plus a
SHA-256 checksum file.

https://github.com/pyraxxz/Floating-Bar/releases

Current release: **v0.1.15**.

Prefer building it yourself? Right-click `build.ps1` → *Run with
PowerShell* (or run the equivalent manually):

```bat
pip install pyinstaller
pyinstaller --onefile --noconsole --name FloatingBar main.py
```

---

## How sending works (v0.1.15)

Sending is designed to avoid bringing Telegram to the foreground. The
production path is a hardened cascade:

1. Capture the window that owned focus when the orb was opened.
2. Locate Telegram by process image name. If the captured foreground HWND
   is a Telegram window, prefer that exact window; otherwise fall back to
   normal Telegram discovery.
3. Capture the Telegram top-level `(HWND, PID)` scope for the send.
4. Post an invisible click into the chosen compose field.
5. Ask Windows which child HWND currently owns focus and, when it belongs to
   Telegram, post UTF-16 `WM_CHAR` units directly to that child. Fall back to
   the top-level Telegram window only when necessary.
6. Audit the Edit controls using **value lengths only**. If another Edit is
   already non-empty (for example, the search field), prefer the positive-value
   Edit that geometrically overlaps the selected compose.
7. Remember the confirmed inner compose runtime ID only for the current
   Telegram window/process. After Telegram restarts, or when the remembered
   control no longer has valid lower-window compose geometry, the cache is
   discarded and the compose is rediscovered.
8. Before every critical click/keypress, verify that the same Telegram
   top-level HWND/PID is still the target. A restart or window replacement
   aborts the current send safely instead of risking delivery into a changed
   target.
9. When the compose is verifiably holding the text, submit through the
   Send-button/Enter cascade with strict voice/mic rejection. Unnamed button
   candidates must remain in the compose row and to its right; unrelated
   lower-window controls are ignored.
10. Submission verification is bounded and asynchronous: a send click is
    allowed time to clear the compose before it is classified as a failure,
    reducing false failures and avoiding unnecessary duplicate fallback sends.
11. When the landing cannot be verified, only an explicitly named `Send`
    button can be clicked. Ambiguous controls are rejected; posted Enter
    combinations are the fallback.
12. The injector result is converted to a typed `SubmissionEvidence` state
    (`failed`, `submitted`, `verified`, `verification-unavailable`, or
    `unknown`) before UI presentation. The UI does not infer confirmation by
    parsing strategy-name substrings.

### Failure recovery and status feedback

A genuinely failed send keeps the unsent text as a **session-only retry draft**.
The next time you open the orb, the draft is restored and selected so you can
retry or replace it quickly. The draft is held only in process memory and is
cleared when you begin typing a new message or after a successful send.

A path that completes without a reliable read-back confirmation is deliberately
**amber**, not green. The message is not automatically offered as a retry,
because it may already have reached Telegram and an automatic retry could
create a duplicate.

Internally, the send result distinguishes confirmed sends from submitted-but-
uncertain and verification-unavailable outcomes. This prevents an optimistic
strategy label from being presented as proof that Telegram accepted the message.

The process is initialized as **per-monitor DPI aware** before Tk creates its
first window. This keeps Tk/UIA geometry and posted client coordinates more
consistent when Windows uses different scaling factors on different monitors.

The aggressive focus-stealing/clipboard recovery remains opt-in through
`ALLOW_FOCUS_STEAL = False`. Clipboard recovery refuses to paste when setting
the relay text on the clipboard fails.

### Why the implementation avoids UIA `SetValue`

Telegram's Qt accessibility tree can expose a wrapper Edit whose
`ValuePattern` does not write correctly. Earlier real traces also showed
that automation writes could change focus and bring Telegram forward. The
production injector therefore uses UI Automation for discovery, geometry,
value-length auditing, and button identification — but not for writing the
message text through `ValuePattern.SetValue`.

### Telegram's "Send on Ctrl+Enter" setting

The app presses the configured combo first and the alternate combo as a
fallback. `ENTER_SEND_MODE = "ctrl+enter"` changes which is tried first.

---

## The orb's status colors

| Color | Meaning |
|---|---|
| blue | Telegram window located — ready |
| gray | Telegram not found |
| amber pulse | injection in flight |
| amber flash | send path completed but could not be confirmed |
| green flash | sent and verified |
| red flash | failed; the draft is preserved for retry |

---

## The right-click menu (and how to quit)

There's no taskbar entry, so the orb has a right-click menu: it shows the
version you're running, opens the trace folder, and has **Quit** — the
only correct way to close the app.

## The trace log — what to send when something misbehaves

Every send attempt writes a stage-by-stage trace (strategy labels,
pattern availability, verification results, button names, geometry,
focused-HWND decisions, target-scope decisions — **never message content**)
to:

```
%APPDATA%\FloatingBar\trace.log
```

Right-click the orb → **Open trace folder**, and share the log after a
failed send — it pinpoints exactly which stage of the cascade your
Telegram build rejects. The log is truncated at every app start, so it
only ever holds the current session.

## Diagnostics

A read-only diagnostic that finds the Telegram window and ranks its Edit
controls without reading message content:

```bat
python tools/diagnose.py
```

It lists the focused HWND, chosen compose click point, Edit runtime IDs,
and every Button near the compose with its accessible name and
InvokePattern availability.

A live end-to-end test uses the **same hardened injector as the app**:

```bat
python tools/diagnose.py --send "test 123"
```

---

## Troubleshooting

* **A solid dark box instead of transparency** — your Tk build mishandles
  `-alpha` combined with `-transparentcolor`. Set `USE_WINDOW_ALPHA = False`
  in `config.py`; the color-key alone keeps working.
* **Text never arrives** — run `tools/diagnose.py`; it prints the selected
  compose geometry, focused HWND, and UIA control information. If no `Edit`
  control is listed, no chat is open in Telegram.
* **"Telegram Desktop doesn't seem to be running"** while it is — a
  portable/repackaged Telegram may rename the exe. Edit
  `PROCESS_NAME_RE` / `TITLE_FALLBACK_RE` in `config.py`.
* **Multiple Telegram windows** — when the orb was opened while Telegram
  itself was active, v0.1.13+ preserves that exact Telegram window. When the
  orb was opened from another application, normal Telegram discovery is used.
* **Send could not be confirmed** — do not immediately retry unless you have
  checked the chat. v0.1.15 deliberately keeps uncertain outcomes amber to
  avoid duplicate sends.
* **A previous send failed** — open the orb to recover the previous text as a
  selected draft. Typing anything new replaces that draft.
* **The orb is blue but sending fails** — most likely UIPI: don't run
  Floating Bar (or Telegram) elevated while the other runs normally.
* **Mixed-DPI/multi-monitor setup** — v0.1.11+ enables per-monitor DPI
  awareness before creating the UI. Restart the app after changing Windows
  display scaling.
* **Telegram restarts during a send** — v0.1.12+ aborts that send safely and
  asks you to try again rather than continuing against a stale HWND.
* **Telegram must not be minimized.** Background (behind other windows)
  is supported — minimized windows cannot reliably receive the posted
  client-coordinate clicks.

## Privacy

No message content is ever logged, stored, or persisted — the app holds
the typed text in memory only until it is injected. Verification uses
lengths/booleans and never records message content. No telemetry. No
network. No Telegram credentials.

## Release integrity

Release builds are validated on Windows before publication. The release
workflow avoids publishing a queued build if `main` has moved on, serializes
versioned releases, and publishes `FloatingBar.exe.sha256` alongside the EXE
so the downloaded binary can be integrity-checked independently.

## Limitations (accepted, by design)

* Telegram Desktop on Windows only (v1).
* The compose box is located heuristically and then refined using real
  runtime geometry and current-window confirmation.
* Injection targets **whatever chat is currently open** in the selected
  Telegram window — that's the feature, and also the footprint: if you send
  while the wrong chat is focused, the text goes there.
* If the opt-in clipboard strategy runs while another app is actively
  changing the clipboard, there is a small race window during restore;
  the guard retries and preserves all captured HGLOBAL-backed formats.
