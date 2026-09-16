# Floating Bar — master implementation roadmap

This is the project-level roadmap. `IMPLEMENTATION_NOTES.md` remains the detailed engineering record; this file answers “what exists, what is in progress, and what is next.”

## Product goal

Turn the Windows floating orb into a background-input layer:

`orb → background apps → app capability → target/control → type → submit → verify`

The app should let the user work in the foreground while sending/replying through selected background applications without stealing focus.

## Current state

### Completed foundation

- [x] Always-on-top orb/bar UI
- [x] Telegram Desktop background sending without normal foreground restoration
- [x] Exact Telegram HWND/PID leases and stale-target guards
- [x] UTF-16 `WM_CHAR` text delivery
- [x] Nested compose and Send-button evidence handling
- [x] Typed submission evidence and transaction lifecycle
- [x] Failed-send retry draft and explicit retry UX
- [x] Content-free background-window discovery
- [x] Hover application picker
- [x] Second-level app action popup
- [x] Telegram chat picker foundation
- [x] Generic background typing target with exact HWND/PID validation
- [x] Generic retry preserves original HWND/PID scope
- [x] Windows CI compile + regression suite + PyInstaller build
- [x] Release workflow separated from ordinary development pushes

### Current grouped milestone — Adapter Architecture

- [x] Central `app_adapters.py` registry for supported executables
- [x] Picker derives labels, capabilities, and actions from the registry
- [x] Production routing derives adapter identity from the registry
- [x] Tests cover aliases and adapter metadata
- [ ] Replace the generic type adapter with per-app target/control discovery
- [ ] Add per-app send verification

## Phase 2 — Finish the current UX and reliability layer

- [ ] Make hover movement between orb → app list → action menu more forgiving
- [ ] Show useful “unavailable/unsupported” feedback instead of silently failing
- [ ] Keep selected app identity visible in the active bar without exposing window titles
- [ ] Add deterministic tests for picker hover state transitions where practical
- [ ] Complete generic-app retry/recovery coverage for all supported adapters

## Phase 3 — Real application adapters

### Telegram

- [x] Window discovery
- [x] Chat picker
- [x] Background selection
- [x] Safe send transaction
- [x] Retry and evidence lifecycle
- [ ] Improve same-window chat-switch detection without message-content reads
- [ ] Validate against traces from multiple Telegram Desktop builds
- [ ] Build real desktop smoke matrix

### Terminal

- [x] Discovery and generic typing path
- [ ] Dedicated terminal adapter
- [ ] Explicit console-control targeting
- [ ] Submission semantics appropriate to terminal
- [ ] Verification/retry behavior

### WhatsApp

- [x] Discovery and generic typing foundation
- [ ] Dedicated composer discovery
- [ ] Chat/conversation picker
- [ ] Background submit
- [ ] Verification

### Discord

- [x] Discovery and generic typing foundation
- [ ] Dedicated composer discovery
- [ ] Server/channel/DM targeting model
- [ ] Background submit
- [ ] Verification

### Slack

- [x] Discovery and generic typing foundation
- [ ] Dedicated composer discovery
- [ ] Conversation targeting
- [ ] Background submit
- [ ] Verification

### Microsoft Teams

- [x] Discovery and generic typing foundation
- [ ] Dedicated composer discovery
- [ ] Conversation targeting
- [ ] Background submit
- [ ] Verification

## Phase 4 — Target/control intelligence

The key transition is from “whatever control currently has focus” to “the correct input control for this application.”

- [ ] Inspect UI Automation structure without reading message content
- [ ] Identify editable controls by role/class/capability
- [ ] Reject search/navigation fields when a composer is available
- [ ] Support multiple candidate controls with evidence scoring
- [ ] Pin the selected control for the duration of a send
- [ ] Abort safely when the control or process changes

## Phase 5 — Conversation intelligence

- [ ] Identify useful/reply-needed chats without scraping message content
- [ ] Prioritize unread/relevant conversations where application APIs/UI expose safe structural signals
- [ ] Keep chat selection content-free where possible
- [ ] Refresh/revalidate rows immediately before background selection
- [ ] Avoid assuming visual ordering is stable across app versions

## Phase 6 — Verification and reliability

Every adapter should eventually produce one of:

`verified | submitted-but-unverified | failed | blocked`

- [ ] App-specific verification hooks
- [ ] Bounded post-send checks
- [ ] Duplicate-send-safe retry rules
- [ ] Clear user feedback for blocked targets
- [ ] Trace adapter, target, and verification stages without message content

## Phase 7 — Real Windows validation

- [ ] Windows 10 and Windows 11 smoke tests
- [ ] Mixed-DPI/multi-monitor tests
- [ ] Minimized/background window tests
- [ ] Multiple-window tests per supported app
- [ ] App restart/process replacement tests
- [ ] Unicode/emoji/long-text tests
- [ ] Repeated-send tests
- [ ] App-version trace collection

## Phase 8 — Product release

- [ ] Final supported-application matrix
- [ ] Installation/startup behavior
- [ ] Packaging and clean upgrade path
- [ ] User documentation
- [ ] Troubleshooting guide
- [ ] Meaningful milestone release after real desktop validation

## Working rule

Implementation should proceed in grouped milestones, not isolated micro-commits. Each batch should move a user-visible capability or a major architectural boundary forward, add regression coverage, and finish with Windows CI validation before the next large feature batch.
