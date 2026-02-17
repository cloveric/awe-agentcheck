# Architecture Flow

Date: 2026-02-18

## 1) Control Plane

```text
Operator / Script
    |
    |  REST (create/start/cancel/force-fail/query/tree/history)
    v
FastAPI (awe_agentcheck.api)
    |
    v
OrchestratorService
    |
    v
WorkflowEngine
```

## 2) Execution Flow (per task)

```text
create task (queued)
  -> if self_loop_mode=0:
       start task -> proposal consensus rounds (running)
         when debate_mode=1:
           1) reviewer precheck pass
           2) author proposal/reply
           3) reviewer proposal review
         round counted only on reviewer consensus
         bounded retries per round; if no consensus -> failed_gate(proposal_consensus_not_reached)
       after target consensus rounds -> waiting_manual
       author decision:
         approve -> queued -> start task (running, full workflow)
         reject -> canceled
  -> if self_loop_mode=1:
       start task (running)
         -> round 1..N
            1) reviewer-first debate/precheck (optional, debate_mode=1)
            2) discussion (author CLI)
            3) implementation (author CLI)
            4) review (reviewer CLI(s))
            5) verify (test command + lint command)
            6) gate (medium policy)
         -> terminal: passed | failed_gate | failed_system | canceled

Task-level strategy controls:

- `evolution_level`:
  - `0` fix-only
  - `1` guided evolution
  - `2` proactive evolution
- `repair_mode`:
  - `minimal` smallest safe patch
  - `balanced` root-cause + focused scope (default)
  - `structural` allows deeper refactor
- `evolve_until`: optional discussion/evolution wall-clock deadline (reaches deadline -> graceful cancel with `deadline_reached`)
- precedence rule:
  - if `evolve_until` is set, deadline is primary stop condition
  - if `evolve_until` is empty, `max_rounds` is used
- `sandbox_mode`:
  - `1` execute in sandbox workspace (default `<project>-lab`)
  - `0` execute directly in project workspace
- `auto_merge`:
  - `1` default, auto-fusion on `passed` (merge/changelog/snapshot)
  - `0` disable fusion and keep task outputs in artifacts/sandbox only
- default sandbox allocation:
  - if sandbox path not provided, allocate unique per-task workspace:
    - `<project>-lab/<timestamp>-<id>`
  - after `passed + auto_merge_completed`, generated sandbox is auto-cleaned
- `self_loop_mode`:
  - `0` proposal consensus rounds first, then wait author confirmation before implementation (default)
  - `1` fully autonomous loop
- `plain_mode`:
  - `1` beginner-readable output style (default)
  - `0` raw technical style
- `stream_mode`:
  - `1` emit realtime participant stream chunks (default)
  - `0` emit stage-level outputs only
- `debate_mode`:
  - `1` enable reviewer-first debate stages (default)
  - `0` skip debate stages
```

## 3) Participant Model

- ID format: `provider#alias`
- Examples:
  - `claude#author-A`
  - `codex#review-B`
  - `gemini#review-C` (cross-provider review role)
- Supports cross-provider and same-provider multi-session review topologies.

## 4) Overnight Loop (auto-evolve)

```text
start_overnight_until_7.ps1
  -> start/reuse API
  -> launch overnight_autoevolve.py
      -> create auto-start task
      -> wait terminal
      -> append overnight markdown log
      -> repeat until deadline
```

## 5) Resilience Rules

- Single-instance lock: prevents duplicate overnight runners.
- Concurrency cap: limits simultaneously running tasks.
- Fallback switching:
  - Claude-side system failure -> switch to Codex fallback.
  - Codex-side system failure (`command_timeout`/`command_not_found`/`provider_limit`) -> switch back to primary.
- Provider-limit cooldown:
  - Claude `provider_limit` triggers temporary primary disable window.
- Watchdog timeout:
  - If a task exceeds `task-timeout-seconds`, runner issues cancel + `force-fail` (`watchdog_timeout`) to unblock progression.

## 6) Observability Surfaces

- API: `/api/stats`
  - `status_counts`
  - `reason_bucket_counts`
  - `provider_error_counts`
  - recent terminal rates and mean duration
- API: `/api/workspace-tree` for project file structure
- API: `/api/project-history` for project-level historical ledger:
  - `core_findings`
  - `revisions`
  - `disputes`
  - `next_steps`
- API: `/api/tasks/{task_id}/author-decision` for manual approve/reject in waiting state
- Web console: `http://127.0.0.1:8000/`
- Artifacts per task: `.agents/threads/<task_id>/`
- Overnight logs: `.agents/overnight/`

## 7) Monitor UI Layout

```text
Left column
  top    -> Project structure tree (directories + files)
  bottom -> Roles / sessions (participant grouped)

Right column
  top    -> scope + task controls
  middle -> dialogue stream
  lower  -> project history ledger
  bottom -> task creation
```

## 8) Persistence Defaults

- If `AWE_DATABASE_URL` is unset, startup scripts default to local SQLite:
  - `.agents/runtime/awe-agentcheck.sqlite3`
- This keeps project/task history across API restarts.
