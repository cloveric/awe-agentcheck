# Testing Target Policy

Date: 2026-02-19

## Decision

Use dual target modes:

1. Fusion mode for direct self-evolution into main program repo.
2. Sandbox mode for risky experiments and reproducible benchmark loops.

Primary fusion path:

- `C:/Users/hangw/awe-agentcheck`

Primary sandbox path:

- `C:/Users/hangw/awe-agentcheck-lab`

## Rationale

1. Avoid accidental impact on active business projects.
2. Keep test data and automated edits isolated.
3. Improve reproducibility of author/reviewer loop experiments.
4. Enable eventual open-source benchmark quality improvements.

## Rules

1. Do not use `autodcf` as default target for generic orchestration tests.
2. Default task policy is `sandbox_mode=1` and `self_loop_mode=0` (author confirmation before implementation).
3. Use sandbox mode first for risky/unknown changes, then promote to fusion mode.
4. For unattended overnight runs, prefer `self_loop_mode=1` to avoid waiting_manual stalls.
5. Keep sandbox scenarios versioned and deterministic.
6. Store benchmark tasks and expected outcomes in sandbox docs/tests.
7. Use the fixed benchmark suite for regression comparisons:
   - task set: `ops/benchmark_tasks.json`
   - runner: `scripts/benchmark_harness.py`
   - reports: `.agents/benchmarks/benchmark-*.json|md`

## Follow-up

When implementing new workflow features in `awe-agentcheck`, add/extend tests against `awe-agentcheck-lab` first.
