# Floating Bar desktop smoke test

This checklist is for real Windows/Telegram validation. It does not require sending private message content into logs; use harmless test text only when a live send is explicitly required.

## Before starting

- Windows 10 or 11.
- Telegram Desktop installed and running normally, not elevated.
- Floating Bar launched normally, not elevated.
- One or more Telegram chats open.
- For mixed-DPI testing, use the real monitor/scaling configuration where the problem occurs.

## 1. Read-only preflight

With Telegram open to a chat, run from the repository root:

```bat
python tools/diagnose.py --preflight
```

Expected:

- `ready=True`.
- A non-zero Telegram HWND/PID.
- `minimized=False`.
- `scope_stable=True`.
- A usable compose click point.
- Either a safe Send candidate or an explicit Enter-fallback note.

The command must not change foreground focus, type, click, or touch the clipboard.

## 2. Basic invisible send

Open Telegram to a harmless test chat. Click the Floating Bar orb, enter a short test message, and press Enter.

Expected:

- Telegram does not need to be raised to the foreground.
- The text lands in the intended chat.
- The orb reports green only when submission is actually verified.

## 3. Multiple Telegram windows

Open two Telegram windows with different chats. Put window A in the foreground, open the orb, then send.

Expected: window A receives the message.

Repeat with window B.

Expected: window B receives the message.

## 4. Telegram restart protection

Open the orb, then restart Telegram before pressing Enter.

Expected: the send is refused safely rather than targeting the new Telegram window accidentally. The failed text should be recoverable through the retry flow.

## 5. Chat-switch protection

Open the orb while Telegram chat A is active. Switch Telegram to chat B before pressing Enter (using a separate method that can change the Telegram UI while the bar is open).

Expected: the send is refused safely and does not silently send to B.

## 6. Failed-send retry

Cause a harmless failed send, then use the orb's right-click menu and choose **Retry failed draft**.

Expected:

- The draft is restored and selected.
- Nothing is sent automatically.
- Pressing Enter performs the deliberate retry.
- If the original Telegram context changed, the retry is blocked until the intended context is restored.

## 7. Unverified result

Test a Telegram state where the injector can submit but cannot read back enough evidence to confirm the result.

Expected: amber/unverified feedback, no automatic retry, and no false green success.

## 8. Mixed DPI / multiple monitors

Repeat the basic send with Floating Bar on a monitor whose scaling differs from Telegram's monitor.

Expected: the compose click lands correctly and no obvious coordinate drift occurs.

## 9. Emoji and whitespace

Use harmless test text containing:

- an emoji such as `🙂`;
- intentional leading/trailing spaces.

Expected: the emoji remains intact and intentional whitespace is preserved.

## 10. Trace collection

After any failure:

```bat
python tools/diagnose.py --preflight
```

Then open the trace folder from the orb's right-click menu. Share `trace.log` only after confirming it contains no message content; the application is designed to log lengths, geometry, identifiers, stage names, scores, and booleans rather than message text.

## Milestone acceptance

Do not create a new public release solely because one test passes. A release milestone should require the accumulated automated suite to remain green plus successful real-desktop smoke testing across the scenarios relevant to that milestone.
