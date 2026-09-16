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
- [x] Generic target structural probe and editable-control discovery
- [x] Generic retry preserves original HWND/PID scope and adapter identity
- [x] Structural candidate scoring without reading text/value content
- [x] Exact input-control pinning and revalidation for generic background sends
- [x] Windows CI compile + regression suite + PyInstaller build
- [x] Release workflow separated from ordinary development pushes
- [x] Background picker can include minimized application windows
- [x] Minimized targets are allowed into structural probing; input discovery remains the safety gate

### Completed grouped milestone — Adapter Architecture

- [x] Central `app_adapters.py` registry for supported executables
- [x] Picker derives labels, capabilities, and actions from the registry
- [x] Production routing derives adapter identity from the registry
- [x] Adapter metadata defines target mode, submit mode, and verification mode
- [x] Tests cover aliases, capabilities, and adapter metadata
- [x] Adapter target factory separates per-app implementations from UI routing
- [x] Dedicated Terminal target rejects focused controls that are not structurally discovered as editable
- [x] Dedicated chat composer target rejects controls outside the structural Edit/Document inventory
- [x] Adapter evidence policy prevents unverified adapters from claiming `VERIFIED`
- [x] Telegram verification contract is explicitly `compose-clear`
- [ ] Add app-specific verification implementations for WhatsApp/Discord/Slack/Teams/terminal
- [x] Add dedicated structural target/control adapters for chat applications

## Phase 2 — Finish the current UX and reliability layer

- [x] Make hover movement between orb → app list → action menu more forgiving
- [x] Show safe picker availability/action affordances instead of silent unsupported selection
- [x] Keep selected app identity visible in the active bar without exposing window titles
- [x] Add deterministic tests for picker hover state transitions where practical
- [x] Complete generic-app retry/recovery coverage for structurally pinned input controls
- [x] Guard delayed picker callbacks against stale app/chat selections
- [x] Keep minimized background applications eligible for selection while retaining structural target safety checks

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

- [x] Discovery and adapter capability contract
- [x] Dedicated structural target adapter
- [x] Exact-scope binding
- [x] Exact-control revalidation for pinned sends
- [x] Prefer a discovered console control when focus is elsewhere
- [ ] Explicit console-control targeting across terminal variants
- [ ] Submission semantics appropriate to terminal
- [ ] Verification/retry behavior

### WhatsApp

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [ ] Background submit
- [ ] Verification

### Discord

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [ ] Server/channel/DM targeting model
- [ ] Background submit
- [ ] Verification

### Slack

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [ ] Conversation targeting refinements
- [ ] Background submit
- [ ] Verification

### Microsoft Teams

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [ ] Conversation targeting refinements
- [ ] Background submit
- [ ] Verification

## Phase 4 — Target/control intelligence

The key transition is from “whatever control currently has focus” to “the correct input control for this application.”

- [x] Inspect UI Automation structure without reading message content
- [x] Identify editable controls by role/class/capability
- [x] Prefer composer-shaped controls over focused search/navigation controls where a composer is available
- [x] Support multiple candidate controls with deterministic structural scoring
- [x] Pin the selected control for the duration of a send
- [x] Abort safely when the control or process changes
- [x] Revalidate pinned control identity against HWND reuse
- [x] Allow responsive geometry changes without invalidating an otherwise stable control identity

## Phase 5 — Conversation intelligence

- [ ] Identify useful/reply-needed chats without scraping message content
- [ ] Prioritize unread/relevant conversations where application APIs/UI expose safe structural signals
- [x] Keep chat selection content-free where possible
- [x] Refresh/revalidate rows immediately before background selection
- [x] Prefer UI Automation runtime identity when available; use structural control identity as a guarded fallback
- [x] Keep the currently selected conversation visible in the short picker window
- [x] Avoid treating visual ordering as conversation identity

## Phase 6 — Verification and reliability

Every adapter should eventually produce one of:

`verified | submitted-but-unverified | failed | blocked`

- [x] Central typed evidence model
- [x] Adapter-specific verification contract in the registry
- [x] Conservative evidence normalization that cannot upgrade unsupported adapters
- [ ] App-specific verification hooks for generic chat and terminal adapters
- [ ] Bounded post-send checks
- [ ] Duplicate-send-safe retry rules
- [x] Clear user feedback for blocked targets
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
