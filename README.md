# awe-agentcheck

Professional multi-CLI orchestration platform for agent author/reviewer workflows, with live observability and operator controls.

## Highlights

- Full lifecycle loop: `discussion -> implementation -> review -> verification -> gate`
- Medium gate policy: requires tests + lint + non-blocking reviewer verdicts
- Participant abstraction: `provider#alias` (for example `claude#author-A`, `codex#review-B`)
- Task-scoped artifact trail in `.agents/threads/<task_id>/`
- Default safe execution profile:
  - `sandbox_mode=1` (run in `*-lab` workspace by default)
  - `self_loop_mode=0` (discussion/review first, then wait author decision)
- Operator web console with:
  - project tree
  - role/session filters
  - conversation stream
  - force-fail / start / cancel controls
  - multi-theme UI (`Neon Grid`, `Terminal Pixel`, `Executive Glass`)
- Auto-fusion mode (default `on`):
  - auto merge changed outputs to target workspace
  - auto-generate `CHANGELOG.auto.md`
  - auto-create snapshot archives
- Local observability stack: OpenTelemetry + Prometheus + Loki + Tempo + Grafana

## Architecture

```text
Task Request
   |
   v
API (FastAPI) ----> Repository (PostgreSQL or In-Memory fallback)
   |                               |
   v                               v
Orchestrator Service ----------> Artifact Store (.agents/threads)
   |                               |
   v                               v
CLI Providers (Codex / Claude)  Events / State / Reports
   |
   v
Gate Decision ----> Auto Fusion (optional) ----> Changelog + Snapshot
        |
        +--> WAITING_MANUAL (author confirmation) when self_loop_mode=0
```

## Quick Start (Windows / PowerShell)

```powershell
cd C:/Users/hangw/awe-agentcheck
py -m pip install -e .[dev]
```

Start API:

```powershell
$env:AWE_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/awe_agentcheck"
$env:AWE_ARTIFACT_ROOT="C:/Users/hangw/awe-agentcheck/.agents"
$env:AWE_CLAUDE_COMMAND="claude -p --dangerously-skip-permissions --effort low"
$env:AWE_CODEX_COMMAND="codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=low"
$env:AWE_PARTICIPANT_TIMEOUT_SECONDS="240"
$env:AWE_COMMAND_TIMEOUT_SECONDS="300"
$env:AWE_PARTICIPANT_TIMEOUT_RETRIES="1"
$env:AWE_MAX_CONCURRENT_RUNNING_TASKS="1"
# Optional smoke mode:
# $env:AWE_DRY_RUN="true"

$env:PYTHONPATH="C:/Users/hangw/awe-agentcheck/src"
py -m uvicorn awe_agentcheck.main:app --reload --port 8000
```

Open dashboard:

- `http://localhost:8000/`

## CLI Usage

Create and optionally start a task:

```powershell
$env:PYTHONPATH="C:/Users/hangw/awe-agentcheck/src"
py -m awe_agentcheck.cli run `
  --task "Improve monitor signal quality" `
  --author "claude#author-A" `
  --reviewer "codex#review-B" `
  --reviewer "claude#review-C" `
  --evolution-level 1 `
  --sandbox-mode 1 `
  --self-loop-mode 0 `
  --evolve-until "2026-02-13 06:00" `
  --workspace-path "C:/Users/hangw/awe-agentcheck" `
  --auto-start
```

Disable auto-fusion for one run:

```powershell
py -m awe_agentcheck.cli run `
  --task "Experiment branch" `
  --author "codex#author-A" `
  --reviewer "claude#review-B" `
  --sandbox-mode 0 `
  --self-loop-mode 1 `
  --workspace-path "C:/Users/hangw/awe-agentcheck" `
  --no-auto-merge
```

Use explicit merge target:

```powershell
py -m awe_agentcheck.cli run `
  --task "Cross-workspace merge" `
  --author "claude#author-A" `
  --reviewer "codex#review-B" `
  --workspace-path "C:/Users/hangw/awe-agentcheck-lab" `
  --merge-target-path "C:/Users/hangw/awe-agentcheck"
```

Inspect:

```powershell
py -m awe_agentcheck.cli tasks --limit 20
py -m awe_agentcheck.cli status task-1
py -m awe_agentcheck.cli events task-1
py -m awe_agentcheck.cli stats
```

Control:

```powershell
py -m awe_agentcheck.cli start task-1
py -m awe_agentcheck.cli cancel task-1
py -m awe_agentcheck.cli force-fail task-1 --reason "watchdog_timeout: manual operator intervention"
py -m awe_agentcheck.cli decide task-1 --approve --auto-start
```

## API Surface

- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/start`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tasks/{task_id}/events`
- `POST /api/tasks/{task_id}/gate`
- `POST /api/tasks/{task_id}/force-fail`
- `POST /api/tasks/{task_id}/author-decision`
- `GET /api/workspace-tree`
- `GET /api/stats`

## Auto Fusion Artifacts

When a task finishes with `passed` and `auto_merge=1`:

- changed files are merged to target workspace (in-place by default)
- `CHANGELOG.auto.md` is generated in merge target root
- snapshot zip is created under `.agents/snapshots/`
- task artifact `auto_merge_summary.json` is written under `.agents/threads/<task_id>/artifacts/`

When `self_loop_mode=0`, first `start` moves task into `waiting_manual` and writes proposal artifact:

- `.agents/threads/<task_id>/artifacts/pending_proposal.json`

Author approves/rejects through API/CLI/Web:

- approve => back to `queued` (`last_gate_reason=author_approved`) and can start execution
- reject => `canceled` (`last_gate_reason=author_rejected`)

## Observability

Local stack:

- `docker-compose.observability.yml`
- `ops/otel-collector-config.yaml`
- `ops/prometheus.yml`
- `ops/tempo.yaml`

## Quality Gate

Run checks:

```powershell
cd C:/Users/hangw/awe-agentcheck
py -m ruff check .
py -m pytest -q
```

Self-smoke test:

```powershell
py scripts/selftest_local_smoke.py --port 8011
```

## Overnight Automation

Start:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:/Users/hangw/awe-agentcheck/scripts/start_overnight_until_7.ps1"
```

Force restart:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:/Users/hangw/awe-agentcheck/scripts/start_overnight_until_7.ps1" -ForceRestart
```

Stop:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "C:/Users/hangw/awe-agentcheck/scripts/stop_overnight.ps1"
```

## Reference Docs

- `docs/ARCHITECTURE_FLOW.md`
- `docs/RUNBOOK.md`
- `docs/TESTING_TARGET_POLICY.md`
- `docs/SESSION_HANDOFF.md`
- `docs/plans/2026-02-11-initial-implementation.md`
- `docs/plans/2026-02-13-sandbox-and-author-gate.md`
