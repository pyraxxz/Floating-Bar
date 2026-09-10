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

### Optional: one-file exe

```bat
pip install pyinstaller
pyinstaller --onefile --noconsole --name FloatingBar main.py
```

---

## How sending works (the cascade)

Sending never *requires* Telegram to come to the foreground. Strategies
are tried in order, least disruptive first; each stage only runs if the
previous one did not verifiably work:

| Stage | Mechanism | Focus stolen? | Clipboard used? | Verifiable? |
|---|---|---|---|---|
| **A** | UI Automation `ValuePattern.SetValue` + posted Enter key | no | no | yes — read-back compare |
| **A+** | (A set the text but the posted Enter didn't submit) brief focus steal just to press Enter | briefly | no | yes |
| **A2** | raw `WM_CHAR` / `WM_KEYDOWN` posted into Telegram's HWND | no | no | only if the compose exposes ValuePattern |
| **B** | focus steal + paste via clipboard + Enter | briefly | yes — **fully preserved** | no signal available |

Notes:

* **A** is the best case — genuinely invisible. It depends on Telegram's
  Qt compose box implementing `IValueProvider`, which is not guaranteed;
  when absent, A is skipped instantly.
* **A2** works when Telegram's compose box is its internally-focused
  widget. Qt exposes one native HWND per top-level window, so the
  characters land wherever Qt's internal focus is — inherently best-effort.
* **B** is the safety net. It raises Telegram, clears the compose
  deterministically (`Ctrl+A`, `Del`), pastes, hits Enter, and then
  returns focus to the window you were actually working in.
* `WM_KEYDOWN`/`WM_KEYUP` posts carry a properly constructed LPARAM
  (repeat count, scan code, state bits) — zero-LPARAM posts are ignored
  by some Qt builds. `WM_CHAR` is posted per UTF-16 code unit, so emoji
  and astral characters survive injection intact.
* **Clipboard preservation**: strategy B snapshots *every* HGLOBAL-backed
  clipboard format (text, DIB images, file lists, HTML, RTF, app formats)
  and restores them byte-for-byte — a text-only round-trip would destroy
  a screenshot or copied-file clipboard.

### Telegram's "Send on Ctrl+Enter" setting

If you use the Ctrl+Enter send mode, set in `config.py`:

```python
ENTER_SEND_MODE = "ctrl+enter"
```

---

## The orb's status colors

| Color | Meaning |
|---|---|
| blue | Telegram window located — ready |
| gray | Telegram not found (it starts working the moment Telegram opens) |
| amber pulse | injection in flight |
| green flash | sent |
| red flash | failed (expand the bar to see the error message) |

---

## Diagnostics

A read-only diagnostic that finds the Telegram window and ranks its Edit
controls (never reading message content):

```bat
python tools/diagnose.py
```

And a live end-to-end test of the cascade:

```bat
python tools/diagnose.py --send "test 123"
```

## Troubleshooting

* **A solid dark box instead of transparency** — your Tk build mishandles
  `-alpha` combined with `-transparentcolor`. Set `USE_WINDOW_ALPHA = False`
  in `config.py`; the color-key alone keeps working.
* **Text never arrives** — run `tools/diagnose.py`; it prints exactly which
  strategy the compose box supports. If no `Edit` control is listed, no
  chat is open in Telegram.
* **"Telegram Desktop doesn't seem to be running"** while it is — a
  portable/repackaged Telegram may rename the exe. Edit
  `PROCESS_NAME_RE` / `TITLE_FALLBACK_RE` in `config.py`.
* **The orb is blue but sending fails** — most likely UIPI: don't run
  Floating Bar (or Telegram) elevated while the other runs normally.

## Privacy

No message content is ever logged, stored, or persisted — the app holds
the typed text in memory only until it is injected. The verification
read-backs compare the compose box's value against the text we ourselves
just wrote; the value is used for the comparison and immediately discarded.
No telemetry. No network. No Telegram credentials.

## Limitations (accepted, by design)

* Telegram Desktop on Windows only (v1).
* The compose box is located heuristically (largest bottom-half `Edit`
  control) — a future Telegram UI change can break this until the
  heuristic is updated.
* Injection targets **whatever chat is currently open** — that's the
  feature, and also the footprint: if you send while the wrong chat is
  focused, the text goes there.
* If strategy B runs while your clipboard is mid-use by another app,
  there's a small race window on restore (retry-backed, best effort).
