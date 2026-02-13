# AutoEvolve Round 1 Note (EvolutionLevel 0)

## Change
- Added additive replay cursor field `cursor.quick_status_badge` for panel-ready status text.
- Implemented in domain projection only (`src/labcheck/task.py`) with deterministic format:
  - `MODE • #position/total • +elapsedMs`
  - Examples: `LIVE • #3/3 • +331ms`, `PAUSED • #2/3 • +11ms`, `LIVE • #0/0 • +0ms`
- No field removals/renames; existing `status_line` and `compact_status` remain unchanged.

## Test evidence
- Added domain coverage:
  - `tests/test_domain.py::test_replay_cursor_quick_status_badge_is_deterministic_for_empty_middle_and_live_last`
- Added API parity coverage:
  - `tests/test_api.py::test_get_replay_exposes_cursor_quick_status_badge_top_level_and_nested`
- Red phase evidence:
  - Both tests failed with `KeyError: 'quick_status_badge'` before implementation.
- Green phase evidence:
  - Targeted: `2 passed`
  - Full suite: `526 passed` via `pytest -q`

## Assumptions
- Operators benefit from a short uppercase mode token (`LIVE`/`PAUSED`/`REPLAYING`) over parsing longer cursor metadata.
- `quick_status_badge` should mirror existing replay mode derivation and elapsed timing semantics already used by `compact_status`.

## Risks
- Additive payload growth: negligible response size increase from one extra cursor string.
- UI consumers might diverge if they independently format badges instead of trusting server-provided `quick_status_badge`.
