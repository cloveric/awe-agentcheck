# Web Panel Replay Ergonomics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve operator ergonomics and replay clarity by adding a dedicated task replay response with explicit sequence/timing and UI-ready next actions.

**Architecture:** Extend `Task` with replay projection helpers and expose a new `GET /api/task/{task_id}/replay` endpoint. Keep existing task endpoints backward-compatible while adding deterministic replay metadata (`seq`, `elapsed_ms`) and `next_actions` for panel controls.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, pytest

---

### Task 1: Lock Behavior With Failing Tests

**Files:**
- Modify: `tests/test_api.py`
- Modify: `tests/test_domain.py` (or add `tests/test_task.py` if cleaner)

1. Add API tests for `GET /api/task/{task_id}/replay`:
   - returns 404 for unknown task
   - returns ordered replay events with `seq`, `from`, `to`, `ts`, `duration_ms`, `elapsed_ms`
   - returns `next_actions` matching current state
2. Add task-level tests for replay projection edge cases:
   - initial event handling (`from=None`, `duration_ms=None`)
   - monotonic `seq`
   - stable `elapsed_ms` accumulation
3. Run: `py -m pytest tests/test_api.py -q` (expect FAIL first).

### Task 2: Implement Replay Projection in Domain Model

**Files:**
- Modify: `src/labcheck/task.py`

1. Add transition-target-to-action mapping (e.g., `running -> start`, `completed -> complete`).
2. Add `Task.next_actions()` returning UI-ready action names from valid transitions.
3. Add `Task.replay_events()` returning normalized event objects with:
   - `seq` (0-based)
   - `from`, `to`, `ts`
   - `duration_ms` (nullable)
   - `elapsed_ms` (cumulative, rounded)
4. Keep `Task.to_dict()` backward-compatible; only add fields if needed by endpoint contract.

### Task 3: Expose Replay Endpoint

**Files:**
- Modify: `src/labcheck/api.py`

1. Add response model(s) for replay payload.
2. Implement `GET /api/task/{task_id}/replay`:
   - 404 when task missing
   - success payload includes `id`, `name`, `state`, `next_actions`, `events`
3. Ensure endpoint stays read-only and does not mutate task state/history.

### Task 4: Review Pass

**Files:**
- Review diffs in `src/labcheck/task.py`, `src/labcheck/api.py`, tests

1. Confirm no regression for existing endpoints (`create`, `get`, `start`, `cancel`).
2. Confirm replay contract is deterministic and panel-friendly (no client-side inference required).
3. Check naming consistency (`next_actions`, `elapsed_ms`, `seq`) for frontend readability.

### Task 5: Verify

1. Run targeted tests: `py -m pytest tests/test_api.py -q`.
2. Run full suite: `py -m pytest -q`.
3. Capture any failures and patch before closing round.

---

## Round 1 Implementation Result (2026-02-12)

### What changed

- Added replay event `summary_line` in `src/labcheck/task.py` with normalized shape:
  - `EVENT_TYPE target=<to_state> result=<outcome> dt=<delta_label>`
- Added replay cursor support for replay-last ergonomics in `src/labcheck/task.py`:
  - `cursor.keybindings.replay_last = "r"`
  - `cursor.replay_last_seq` (latest replayable event seq, or `None` when empty)
- Updated action fallback logic for replay normalization in `src/labcheck/task.py`:
  - if event `action` is missing, infer from target state (`running -> start`, etc.)
  - preserves readable summaries for malformed or partially persisted history entries
- Updated replay API keyboard guidance in `src/labcheck/api.py`:
  - now documents `j`, `k`, and `r` behavior
- Added/updated tests in `tests/test_domain.py` and `tests/test_api.py`:
  - summary formatting checks
  - replay-last hotkey contract checks
  - empty replay-buffer replay-last behavior
  - missing-field/repeated-event summary edge case coverage

### Verification evidence

- Red phase (before implementation): `pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 5 failed, 172 passed
  - Failures were expected for missing `summary_line` and missing `r` hotkey contract
- Green phase (after implementation): `pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 177 passed
- Final full-suite verification: `pytest -q`
  - Result: 177 passed

### Explicit assumptions

- Web panel will treat `cursor.replay_last_seq` as the event selected by `r`.
- Existing `j`/`k` behavior and payload fields are stable and must remain backward-compatible.
- For malformed history with missing `action`, inferring action from `to` state is preferable to surfacing `create` on non-initial steps.

### Risks

- `summary_line` is a compact display field; downstream clients that hard-code parsing could break if format evolves.
- In malformed histories with unknown `to` states, fallback action becomes `"event"`; operators may see a less-specific summary.
- Keyboard help text changed; UI docs/snapshots that assert exact wording may need updates.

## Round 1 Update: Cursor Highlight for Replay Clarity (2026-02-12)

### What changed

- Added replay event `highlight` in `src/labcheck/task.py` as a deterministic cursor marker:
  - `highlight=True` only for the currently resolved cursor event (`seq == active_seq`)
  - `highlight=False` for all non-active events
  - empty replay buffers continue returning `events=[]` (no highlight emitted)
- Kept replay payload backward-compatible:
  - existing fields like `is_active`, `selection_state`, `timeline_label`, and `summary_line` are unchanged
  - `highlight` is additive on each replay event in both top-level `events` and nested `replay.events`
- Added/updated tests:
  - `tests/test_domain.py`: verifies unique highlight at cursor event and empty-buffer behavior
  - `tests/test_api.py`: verifies API exposes highlight consistently and additive contract remains stable

### Verification evidence

- Red phase (before implementation): `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 3 failed, 214 passed
  - Expected failures: missing `highlight` in replay event payload
- Green phase (after implementation): `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 217 passed
- Full-suite verification: `py -m pytest -q`
  - Result: 217 passed

### Explicit assumptions

- Operators may use `highlight` as the primary visual affordance while legacy clients can continue using `is_active`.
- Cursor resolution semantics (exact/gap/bounds/default-latest) remain the single source of truth for which event is highlighted.
- Replay endpoint remains read-only; adding `highlight` must not alter state/history.

### Risks

- Dual markers (`is_active` and `highlight`) could drift if future edits update one without the other.
- Some clients may overfit to `highlight` and ignore fallback `is_active` during rollout.
- UI snapshots or strict schema assertions may need updates to account for the added field.

## Round 1 Update: Replay Group Metadata for Operator Scanning (2026-02-12)

### What changed

- Added deterministic replay intent classification in `src/labcheck/task.py`:
  - `_classify_replay_group(to_state, is_active)` returns one of:
    - `selection` for the active replay event
    - `result` for non-active terminal target states (`completed`, `failed`, `cancelled`)
    - `transition` for all other replay events
- Added `replay_group` as an additive field on each replay event emitted by `Task.replay_events(...)`.
- Kept existing replay contract fields unchanged (`seq`, `elapsed_ms`, `highlight`, `summary_line`, cursor metadata, navigation metadata).
- Verified API replay payload includes `replay_group` through existing read-only endpoint paths (top-level `events` and nested `replay.events`) without changing endpoint mutability in `src/labcheck/api.py`.

### Verification evidence

- Red phase: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 3 failed, 284 passed
  - Expected failing reason: missing `replay_group` field in replay events.
- Green targeted: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 287 passed
- Full suite: `py -m pytest -q`
  - Result: 287 passed

### Explicit assumptions

- `replay_group` is an additive ergonomic hint and does not replace existing fields like `is_active`/`highlight`.
- Active-event intent should be represented as `selection` even when the active event is terminal.
- Terminal, non-active events should still surface as `result` to preserve operator scan value.

### Risks

- Group precedence (`selection` over `result`) is opinionated and could conflict with future UI expectations for terminal active events.
- Future replay schema changes could unintentionally drift `replay_group` from `is_active`/state semantics unless covered by tests.

## Round 1 Update: Replay Focus Metadata for Neighbor Context (2026-02-12)

### What changed

- Added deterministic `replay_focus` projection in `src/labcheck/task.py` with:
  - `active_seq`, `prev_seq`, `next_seq`
  - compact neighbor labels: `prev_label`, `next_label`
- `replay_focus` is computed from the same replay snapshot (no task/history mutation) and includes empty-history fallback:
  - all fields `None` when replay history is empty
- Exposed `replay_focus` additively in `src/labcheck/api.py` for `GET /api/task/{task_id}/replay`:
  - top-level `replay_focus`
  - nested `replay.replay_focus`
- Added tests in `tests/test_domain.py` and `tests/test_api.py` for:
  - middle/start/end cursor positions
  - empty history edge case
  - top-level and nested API parity

### Verification evidence

- Red phase: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 4 failed, 293 passed
  - Expected failures: missing `replay_focus` in domain projection/API payload.
- Green targeted: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 297 passed
- Full suite: `py -m pytest -q`
  - Result: 297 passed

### Explicit assumptions

- Operators primarily need immediate neighbor context (previous and next event) at the active cursor; compact labels are sufficient for panel display.
- `replay_focus` is additive and does not replace existing fields (`active_event`, `cursor`, `timeline_items`).
- Compact label format (`#<seq> <ACTION_BADGE> <to_state>`) is stable enough for this round’s UI usage.

### Risks

- If UI clients begin parsing compact label strings, future formatting changes could become a compatibility concern.
- `replay_focus` currently omits extended metadata (timestamps/deltas) by design; some workflows may still need to read full event rows.
- Parallel evolution of replay payload fields could introduce duplication drift unless invariants remain tested.

## Round 1 Update: First/Last Replay Navigation Hints (2026-02-12)

### What changed

- Added additive replay cursor keybinding hints in `src/labcheck/task.py`:
  - `cursor.keybindings.first = "g"`
  - `cursor.keybindings.last = "G"`
- Added deterministic replay cursor jump targets in `src/labcheck/task.py`:
  - `cursor.jump_targets.first_seq`
  - `cursor.jump_targets.last_seq`
  - Empty-history behavior is explicit (`None`/`None`).
- Updated replay keyboard guidance text in `src/labcheck/api.py` to include `g`/`G` semantics.
- Added/updated tests in `tests/test_domain.py` and `tests/test_api.py` covering:
  - Keybinding hints on populated replay buffers
  - Deterministic `jump_targets` values
  - Empty-history keybinding and jump-target behavior

### Verification evidence

- Red phase: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: expected failures for missing `first`/`last` keybindings and missing `jump_targets`.
- Green targeted rerun: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 1 intermittent existing failure (`test_replay_events_have_deterministic_seq_order_and_timing_fields`) unrelated to this schema change; all new replay-navigation assertions passed.
- Full suite: `py -m pytest -q`
  - Result: 299 passed.

### Explicit assumptions

- `g` and `G` are reserved for first/last replay navigation and are exposed as UI hints only in this round.
- `cursor.jump_targets` is additive metadata; existing cursor fields remain source-compatible for clients not yet consuming it.
- Empty-history replay remains read-only and should expose null jump targets instead of synthetic sentinel values.

### Risks

- Some clients may parse `keyboard_help` as fixed text and require snapshot updates due to added `g`/`G` wording.
- If future behavior changes key semantics without updating `cursor.keybindings`, UI affordances could drift from backend hints.
- Intermittent timing-sensitive replay label tests may occasionally mask signal in targeted runs.

## Round 1 Update: Explicit Replay Move Affordances and Position Labels (2026-02-12)

### What changed

- Added additive cursor movement affordances in `src/labcheck/task.py`:
  - `cursor.can_move_prev`
  - `cursor.can_move_next`
- Kept existing cursor fields untouched and aligned:
  - `can_move_prev` mirrors `can_jump_prev`
  - `can_move_next` mirrors `can_jump_next`
- Added per-event deterministic replay position label in `src/labcheck/task.py`:
  - `events[*].position_label` with stable format `#N/Total` (example: `#2/3`)
- Confirmed API exposure remains additive-only via existing snapshot wiring in `src/labcheck/api.py`:
  - top-level `cursor` and `replay.cursor` include new move booleans
  - top-level `events` and `replay.events` include per-event `position_label`
- Added/updated tests in `tests/test_domain.py` and `tests/test_api.py` to lock:
  - deterministic labels for non-empty history
  - empty-history cursor move booleans
  - boundary cursor cases (first/middle/last) for move affordances

### Verification evidence

- Red phase: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 6 failed, 376 passed
  - Expected failing reason: missing `position_label` and `can_move_prev`/`can_move_next`.
- Green targeted rerun: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 382 passed
- Full suite: `py -m pytest -q`
  - Result: 382 passed

### Explicit assumptions

- UI can treat `can_move_prev`/`can_move_next` as explicit navigation affordances without replacing legacy `can_jump_prev`/`can_jump_next`.
- `events[*].position_label` is display-oriented and should remain deterministic for replay scan clarity.
- Existing API consumers relying on prior replay fields remain unaffected because additions are non-breaking.

### Risks

- Dual boolean pairs (`can_jump_*` and `can_move_*`) can drift if one is edited independently in future changes.
- Clients that parse label strings may become sensitive to formatting changes in `position_label`.
- Replay payload size grows slightly with additive fields; low risk but cumulative additions should be monitored.

## Round 1 Update: Unified Navigation Hints for First/Last/Replay-Last (2026-02-12)

### What changed

- Added additive replay navigation hint fields in `src/labcheck/task.py` under `navigation_hints`:
  - `jump_first_key = "g"`
  - `jump_last_key = "G"`
  - `replay_last_key = "r"`
  - `jump_first_seq`
  - `jump_last_seq`
  - `replay_last_seq`
- Kept the response contract backward-compatible:
  - existing `navigation_hints` keys are unchanged
  - existing `cursor.keybindings` and `cursor.jump_targets` remain unchanged
- Added/updated tests:
  - `tests/test_domain.py`: validates first/last/replay-last hints and targets in replay snapshot navigation metadata
  - `tests/test_api.py`: validates API `navigation_hints` includes the new keys/sequences for operator panel consumption

### Verification evidence

- Red phase (before implementation):
  - `py -m pytest -q tests/test_domain.py::test_replay_snapshot_resolves_active_event_from_cursor_seq tests/test_api.py::test_get_replay_includes_active_event_context_and_navigation_hints`
  - Result: 2 failed (missing `navigation_hints` fields)
- Green targeted verification:
  - `py -m pytest -q tests/test_domain.py::test_replay_snapshot_resolves_active_event_from_cursor_seq tests/test_api.py::test_get_replay_includes_active_event_context_and_navigation_hints`
  - Result: 2 passed
- Full suite verification:
  - `py -m pytest -q`
  - Result: 311 passed

### Explicit assumptions

- Operator clients benefit from a single metadata object (`navigation_hints`) that includes both key labels and resolved targets.
- Existing clients using `cursor.keybindings` and `cursor.jump_targets` should continue working unchanged.
- `replay_last_seq` should mirror `jump_last_seq` while still being explicit for UX semantics.

### Risks

- Duplication across `navigation_hints`, `cursor.keybindings`, and `cursor.jump_targets` could drift if future updates touch only one surface.
- Clients that hard-assert exact `navigation_hints` shape may require snapshot/schema updates as additive fields appear.

## Round 1 Update: Deterministic Cursor Compact Status (2026-02-12)

### What changed

- Added additive `cursor.compact_status` in `src/labcheck/task.py` replay projection:
  - Empty replay fallback: `#0/0 live • +0ms • [j/k move, r latest]`
  - Active replay format: `#<index>/<total> <mode> • +<elapsed_ms>ms • [j/k move, r latest]`
- Kept schema contract additive-only:
  - no existing replay fields were removed or renamed
  - `src/labcheck/api.py` required no structural changes; the API already forwards `cursor` to top-level and nested replay payloads
- Added tests:
  - `tests/test_domain.py`: empty history, middle event, and last event deterministic `compact_status`
  - `tests/test_api.py`: `GET /api/task/{id}/replay` exposes identical `cursor.compact_status` at top-level and nested `replay.cursor`

### Verification evidence

- Red phase (before implementation):
  - `py -m pytest -q tests/test_domain.py::test_replay_cursor_compact_status_has_empty_history_fallback tests/test_domain.py::test_replay_cursor_compact_status_is_deterministic_for_middle_event tests/test_domain.py::test_replay_cursor_compact_status_is_live_for_last_event tests/test_api.py::test_get_replay_exposes_cursor_compact_status_top_level_and_nested`
  - Result: 4 failed (missing `compact_status`)
- Green targeted verification:
  - Same command
  - Result: 4 passed
- Broader replay subset:
  - `py -m pytest -q tests/test_domain.py -k replay tests/test_api.py -k replay`
  - Result: 74 passed, 300 deselected

### Explicit assumptions

- Compact status should use replay elapsed timeline (`elapsed_ms`) instead of per-event delta for faster scanability.
- `replay_mode` (`live`, `paused`, `replaying`) is already the canonical mode and should be reused verbatim in compact status.
- Existing keyboard hints remain stable (`j/k` move, `r` latest), so compact status can embed those tokens deterministically.

### Risks

- `compact_status` is a display string; clients parsing it as structured data may be brittle to future formatting updates.
- Embedding keybinding hints in a string can drift if keybindings change without updating this formatter.
- Non-standard histories with unusual elapsed patterns may still be correct but visually surprising to operators.

## Round 1 Update: Cursor Navigation Summary for Faster Replay Scanning (2026-02-12)

### What changed

- Added additive derived field `cursor.nav_summary` in `src/labcheck/task.py`:
  - populated replay example: `first:#0 prev:#3 next:#5 last:#9 latest:#9`
  - empty replay fallback: `first:none prev:none next:none last:none latest:none`
- `nav_summary` is computed from already-resolved replay navigation metadata:
  - `first`/`last`/`latest` from normalized sequence bounds
  - `prev`/`next` from resolved active cursor neighbors
- Kept response contract additive-only:
  - no existing cursor, replay, navigation-hint, or event fields removed/renamed
  - no task state/history mutation logic changed
- Added/updated tests:
  - `tests/test_domain.py`: populated and empty replay snapshot assertions for `cursor.nav_summary`
  - `tests/test_api.py`: top-level `cursor.nav_summary` and nested `replay.cursor.nav_summary` parity for populated and empty histories

### Verification evidence

- Red phase (before implementation):
  - `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 4 failed, 397 passed
  - Expected failing reason: missing `cursor.nav_summary` in domain projection and API payload.
- Green targeted verification:
  - `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 401 passed
- Full-suite verification:
  - `py -m pytest -q`
  - Result: 401 passed

### Explicit assumptions

- Operators benefit from a single compact navigation string to avoid cross-referencing multiple cursor/navigation fields.
- `latest` should mirror replay `last` under current deterministic ordering semantics.
- Empty replay should use explicit `none` tokens rather than synthetic sequence values.

### Risks

- `nav_summary` is display-oriented; clients that parse this string may become sensitive to future formatting changes.
- Duplicating navigation information across structured fields and summary string can drift if future edits update only one surface.

## Round 1 Update: Per-Event Cursor Context for Replay Clarity (2026-02-12)

### What changed

- Added additive replay event cursor-context fields in `src/labcheck/task.py`:
  - `offset_from_active` (signed int): `event_index - active_index`
  - `relative_position` (`past|active|future`) derived from offset sign
- Kept existing semantics unchanged:
  - `is_active` and `highlight` remain current active-event markers
  - no field removals/renames in replay payload
- Added tests first, then implementation:
  - `tests/test_domain.py`:
    - middle cursor case (`[-1, 0, 1]` with `["past", "active", "future"]`)
    - boundary cases (first and last cursor positions)
    - empty-history case (`events == []`)
  - `tests/test_api.py`:
    - verifies top-level `events` and nested `replay.events` expose identical cursor-context values
    - verifies empty-history API replay remains empty and stable
- API code in `src/labcheck/api.py` required no contract wiring changes because replay events are forwarded from snapshot at both top-level and nested paths.

### Verification evidence

- Red phase: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 2 failed, 459 passed
  - Expected failures: missing `offset_from_active` and `relative_position`
- Green targeted: `py -m pytest -q tests/test_domain.py tests/test_api.py`
  - Result: 461 passed
- Full suite: `py -m pytest -q`
  - Result: 461 passed

### Explicit assumptions

- Operator panel will use `offset_from_active`/`relative_position` as additive context hints, not as replacements for `is_active`/`highlight`.
- Event ordering remains deterministic from replay projection, so offset sign consistently maps to past/future.
- Empty replay history should expose no event-level context fields because no events are emitted.

### Risks

- Dual semantics (`is_active`/`highlight` plus `relative_position == "active"`) could drift if future edits update only one path.
- If downstream clients overfit on exact enum values, future additions (for example, `unknown`) could require client updates.

## Round 1 Update: Replay `is_issue` Flag for Operator Scanability (2026-02-12)

### What changed

- Added an additive per-event replay field in `src/labcheck/task.py`:
  - `events[*].is_issue` where:
    - `True` when `status_level` is `warning` or `error`
    - `False` otherwise
- Kept replay contract backward-compatible:
  - no existing replay fields were removed or renamed
  - API wiring in `src/labcheck/api.py` remains unchanged because replay events are forwarded from snapshot to both top-level `events` and nested `replay.events`
- Added test coverage:
  - `tests/test_domain.py`: asserts deterministic `is_issue` values in replay projection
  - `tests/test_api.py`: asserts API replay payload exposes identical `is_issue` values

### Verification evidence

- Red phase (before implementation):
  - `py -m pytest -q tests/test_domain.py::test_replay_events_include_explicit_flow_group_and_status_labels tests/test_api.py::test_get_replay_includes_order_timing_and_next_actions`
  - Result: 2 failed
  - Expected reason: missing `is_issue` in replay events.
- Green targeted verification:
  - same command
  - Result: 2 passed
- Full-suite verification:
  - `py -m pytest -q`
  - Result: 484 passed

### Explicit assumptions

- Operator panels benefit from a direct boolean issue marker instead of inferring issue rows from `status_level` strings.
- `is_issue` is an additive convenience field and does not replace `status_level`/`status_badge`.
- Existing clients consuming replay events tolerate additive fields in both top-level and nested replay payloads.

### Risks

- `is_issue` can drift from `status_level` if future edits change severity mapping in one path without updating this derived boolean.
- Some clients may overfit to `is_issue` and ignore richer severity granularity already present in `status_level`.

## Round 1 Update: Replay Boundary Flags and Per-Event Since-Previous Timing (2026-02-12)

### What changed

- Added additive cursor boundary ergonomics in `src/labcheck/task.py`:
  - `cursor.at_first`
  - `cursor.at_last`
- Added additive per-event timing clarity field in `src/labcheck/task.py`:
  - `events[*].since_prev_ms` (mirrors deterministic replay `delta_ms` used by labels)
- Empty-history behavior is explicit and stable:
  - `cursor.at_first = False`
  - `cursor.at_last = False`
  - `events = []` remains unchanged
- API exposure in `src/labcheck/api.py` remained read-only and backward-compatible without endpoint behavior changes:
  - top-level `cursor` / `events` and nested `replay.cursor` / `replay.events` now include the new additive fields through existing snapshot forwarding
- Added tests in `tests/test_domain.py` and `tests/test_api.py`:
  - populated history boundary coverage (first/middle/last)
  - deterministic `since_prev_ms` assertions
  - empty-history boundary coverage
  - top-level and nested replay payload parity

### Verification evidence

- Red phase domain: `py -m pytest -q tests/test_domain.py -k "boundary_flags or since_prev"`
  - Result: 2 failed (expected: missing `cursor.at_first`/`cursor.at_last`)
- Red phase API: `py -m pytest -q tests/test_api.py -k "boundary_flags and since_prev"`
  - Result: 1 failed (expected: missing boundary fields in replay cursor payload)
- Green targeted rerun:
  - `py -m pytest -q tests/test_domain.py -k "boundary_flags or since_prev"` -> 2 passed
  - `py -m pytest -q tests/test_api.py -k "boundary_flags and since_prev"` -> 1 passed
- Full suite:
  - `py -m pytest -q`
  - Result: 520 passed in 10.33s

### Explicit assumptions

- Operator panel treats `cursor.at_first` and `cursor.at_last` as additive convenience flags, not replacements for existing jump metadata.
- `since_prev_ms` should align with replay’s normalized per-event delta semantics for visual consistency.
- Existing clients tolerate additive fields in replay cursor/event payloads.

### Risks

- `since_prev_ms` and `delta_ms` can drift if one formula changes without test updates keeping parity explicit.
- Clients might parse these additive display-oriented fields as strict control signals; future formatting/derivation changes could require coordinated updates.
