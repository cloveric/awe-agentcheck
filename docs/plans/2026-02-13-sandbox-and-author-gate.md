# Sandbox + Author Gate Plan (Implemented)

Date: 2026-02-13

## Intent

Create a safer default operating model for multi-CLI collaboration:

1. Execute in sandbox workspace by default.
2. Let agents discuss/review first.
3. Ask author before applying code changes.
4. Keep option to switch to direct-main and autonomous loop.

## Final Product Rules

1. `sandbox_mode=1` by default.
2. Sandbox path defaults to `<workspace>-lab` and is auto-created when missing.
3. First-time sandbox run bootstraps project files into sandbox (excluding runtime/cache/git folders).
4. `self_loop_mode=0` by default:
   - first `start` moves task to `waiting_manual`
   - system writes proposal artifact and emits `author_confirmation_required`
   - author can approve/reject
5. `self_loop_mode=1` remains available for autonomous execution.
6. Auto-merge remains an option (default on), and in sandbox mode defaults merge target to project root.

## New API/CLI/UI Controls

### API

- `POST /api/tasks` accepts:
  - `sandbox_mode`
  - `sandbox_workspace_path`
  - `self_loop_mode`
- `POST /api/tasks/{task_id}/author-decision`
  - body: `{ "approve": bool, "note": string|null, "auto_start": bool }`

### CLI

- `run`:
  - `--sandbox-mode 0|1`
  - `--sandbox-workspace-path <path>`
  - `--self-loop-mode 0|1`
- `decide`:
  - `awe-agentcheck decide <task_id> [--approve] [--note "..."] [--auto-start]`

### Web

- Create task form:
  - sandbox mode/path
  - self loop mode
- Task controls:
  - `Approve + Queue`
  - `Approve + Start`
  - `Reject`
- Snapshot cards include:
  - project path
  - workspace path
  - sandbox/self-loop fields

## Artifacts

Manual mode proposal artifact:

- `.agents/threads/<task_id>/artifacts/pending_proposal.json`

Auto-merge summary artifact:

- `.agents/threads/<task_id>/artifacts/auto_merge_summary.json`
