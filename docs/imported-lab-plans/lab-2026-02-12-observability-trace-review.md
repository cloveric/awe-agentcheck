# Observability Trace Review (Round 2, EvolutionLevel 0)

Date: 2026-02-12
Scope: Add normalized `trace_decision_summary` across emitted/dropped workflow traces and metric paths.

## Structured Findings

- Critical: none
- High: none
- Medium: none
- Low:
  - `metric.trace_dropped_total` defaults summary decision to `drop_low_score` when callers do not pass `trace_decision_summary`. Current call sites pass it, so behavior is correct in this code path; risk is only for future direct callers.

## Changed-File Rationale

- `src/labcheck/task.py`
  - Added `_trace_decision_summary(...)` helper to build bounded, normalized summary from `signal_decision`, `decision_reason`, and `signal_quality`.
  - Injected `trace_decision_summary` into normalized payload generation so emitted logs always include it.
  - Added `trace_decision_summary` to all dropped trace branches (malformed, missing required fields, quality-guard failures, low-score drops).
  - Extended `_record_trace_emitted_total(...)` and `_record_trace_dropped_total(...)` to accept/log `trace_decision_summary`, with safe bounded fallback generation for backward compatibility.
- `tests/test_api.py`
  - Added fail-first then passing tests for:
    - emitted traces include `trace_decision_summary`
    - dropped traces include `trace_decision_summary`
    - malformed-drop summary is bounded and valid canonical string

## Verification Evidence

- Targeted tests:
  - `pytest -q tests/test_api.py::test_workflow_trace_emitted_includes_trace_decision_summary tests/test_api.py::test_workflow_trace_dropped_includes_trace_decision_summary tests/test_api.py::test_workflow_trace_malformed_summary_is_bounded_and_valid`
  - Result: 3 passed
- Full regression:
  - `pytest -q`
  - Result: 496 passed
- Path verification:
  - `rg -n "trace_decision_summary" src/labcheck/task.py tests/test_api.py`
  - Result: field present in normalize flow, emit/drop log paths, and emitted/dropped metric paths, plus dedicated tests.

## Assumptions

- Existing trace consumers tolerate additive fields in both log and metric events.
- The bounded max length of 120 characters is sufficient for operator readability while avoiding noisy payload expansion.

## Remaining Risk

- Low: future new call sites to `_record_trace_dropped_total(...)` might omit explicit `trace_decision_summary`, relying on fallback summary semantics.

---

## Round 1 Update: Signal-Quality Reason Canonicalization

Scope: Improve trace signal-quality stability by canonicalizing `signal_quality_reasons` ordering/dedup and aligning emitted/dropped metric payloads.

### What Changed

- `src/labcheck/task.py`
  - Added explicit canonical reason priority (`missing_inputs`, `missing_error_context`, `high_noise_spans`, `retry_noop_low_information`).
  - Updated `_normalize_signal_reason_codes(...)` to:
    - deduplicate valid reason codes
    - emit them in canonical order (not source-order dependent)
    - enforce `<= 3` bounded reasons
  - Extended `_record_trace_emitted_total(...)` and `_record_trace_dropped_total(...)` to accept/log normalized `signal_quality_reasons`.
  - Wired all drop and emit metric call sites to pass reason codes so `metric.trace_emitted_total` and `metric.trace_dropped_total` are directly comparable.
- `tests/test_domain.py`
  - Added fail-first coverage for canonical ordering/dedup behavior.
  - Added metric-level assertions that emitted/dropped totals include bounded canonical `signal_quality_reasons`.
  - Updated prior order-dependent assertions to the new canonical contract.

### Verification Evidence

- Targeted (fail-first then pass):
  - `pytest -q tests/test_domain.py -k "trace_drop_signal_quality_reasons or record_trace_emitted_total_bounds_dimensions_and_increments or record_trace_dropped_total_bounds_trace_decision_confidence"`
  - Result: `5 passed`
- Full regression:
  - `pytest -q`
  - Result: `507 passed in 10.13s`

### Assumptions

- Consumers treat `signal_quality_reasons` as additive metadata and do not require prior source-order semantics.
- Canonical reason precedence improves cross-event comparability more than preserving original arrival order.

### Risks

- Low: downstream tooling that implicitly relied on previous input-order reason lists may show ordering diffs.
- Low: metric payload size increases slightly due to added `signal_quality_reasons`, but remains bounded (`<= 3` reasons).
