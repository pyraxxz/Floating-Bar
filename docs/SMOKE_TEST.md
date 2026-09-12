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

Expected hard prerequisites:

- `ready=True`.
- A non-zero Telegram HWND/PID.
- `minimized=False`.
- `scope_stable=True`.
- A usable compose click point.
- Either a safe Send candidate or an explicit Enter-fallback note.

The reported status should normally be `ready`. `ready-with-degraded-context` is acceptable only when Telegram exposes a generic window title; in that state the exact HWND/PID remains protected, but title-based conversation-switch detection is unavailable.

The command must not change foreground focus, type, click, or touch the clipboard.

## 2. Basic invisible send

Open Telegram to a harmless test chat. Click the Floating Bar orb, enter a short test message, and press Enter.

Expected:

- Telegram does not need to be raised to the foreground.
- The text lands in the intended chat.
- The orb reports green only when submission is actually verified.
- An unverified result is amber and does not become an automatic retry.

## 3. Multiple Telegram windows and target binding

Open two Telegram windows with different chats. Put window A in the foreground, open the orb, then send.

Expected: window A receives the message.

Repeat with window B.

Expected: window B receives the message.

Then start with window A selected and, before pressing Enter, make window B the better/default Telegram discovery candidate.

Expected: the send remains bound to the preflight-selected window A or is refused safely; it must not silently retarget B.

## 4. Telegram restart protection

Open the orb, then restart Telegram before pressing Enter.

Expected: the send is refused safely rather than targeting the new Telegram window accidentally. The failed text should be recoverable through the retry flow.

## 5. Chat-switch protection

Open the orb while Telegram chat A is active. Switch Telegram to chat B before pressing Enter (using a separate method that can change the Telegram UI while the bar is open).

Expected when Telegram exposes a useful changing title: the send is refused safely and does not silently send to B.

When Telegram is configured to expose only a generic title, the test should still verify the stronger HWND/PID protection and document that title-based conversation protection is unavailable for that configuration.

## 6. Failed-send retry

Cause a harmless failed send, then use the orb's right-click menu and choose **Retry failed draft**.

Expected:

- The draft is restored and selected.
- Nothing is sent automatically.
- Pressing Enter performs the deliberate retry.
- If the original Telegram context changed, the retry is blocked until the intended context is restored.
- If Telegram has restarted and the original HWND/PID no longer exists, the replacement window must not be used automatically.

## 7. Send-button safety

Use the diagnostic against a chat where the compose row exposes multiple buttons.

Expected:

- A button named or identified as Send can be selected.
- Voice/record/microphone/audio controls are never selected as Send.
- A named unrelated control such as Attach/Emoji is rejected even when its geometry looks plausible.
- A weak unnamed icon falls through to Enter rather than being clicked.

## 8. Unverified result

Test a Telegram state where the injector can submit but cannot read back enough evidence to confirm the result.

Expected: amber/unverified feedback, no automatic retry, and no false green success.

## 9. Mixed DPI / multiple monitors

Repeat the basic send with Floating Bar on a monitor whose scaling differs from Telegram's monitor.

Expected: the compose click lands correctly and no obvious coordinate drift occurs.

## 10. Emoji and whitespace

Use harmless test text containing:

- an emoji such as `🙂`;
- intentional leading/trailing spaces.

Expected: the emoji remains intact and intentional whitespace is preserved.

## 11. Opt-in recovery safety

Only when `ALLOW_FOCUS_STEAL` is explicitly enabled, exercise a harmless failure that enters the recovery path.

Expected:

- Scope is checked before each critical foreground/focus/keypress action.
- If Telegram is replaced during recovery, the recovery stops rather than continuing against the replacement window.
- Clipboard recovery refuses to paste when the clipboard write itself fails.
- The user's prior foreground window is restored after a recovery attempt.

## 12. Trace collection

After any failure:

```bat
python tools/diagnose.py --preflight
```

Then open the trace folder from the orb's right-click menu. Share `trace.log` only after confirming it contains no message content; the application is designed to log lengths, geometry, identifiers, stage names, scores, and booleans rather than message text.

## Milestone acceptance

Do not create a new public release solely because one test passes. A release milestone should require the accumulated automated suite to remain green, the Windows executable to build successfully, and successful real-desktop smoke testing across the scenarios relevant to that milestone.

For the current 0.2.0 reliability milestone, the acceptance bar is specifically:

1. Windows CI green on the exact release source.
2. Read-only preflight works without changing focus or touching content.
3. Production sends are gated by preflight and remain bound to the selected Telegram HWND/PID.
4. Conversation context protection behaves conservatively when Telegram exposes a useful title and degrades safely when it does not.
5. Send-button selection rejects voice/mic and unrelated named controls.
6. Restart, retry, and opt-in recovery paths stop safely on target replacement.
7. Real Telegram smoke tests confirm actual landing and submission behavior on the user's Windows desktop.
