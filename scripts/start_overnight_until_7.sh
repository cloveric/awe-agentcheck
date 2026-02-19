#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/src"
OVERNIGHT_DIR="$REPO/.agents/overnight"
RUNTIME_DIR="$REPO/.agents/runtime"
SESSIONS_DIR="$OVERNIGHT_DIR/sessions"
LOCK_FILE="$OVERNIGHT_DIR/overnight.lock"
mkdir -p "$SESSIONS_DIR" "$RUNTIME_DIR"

UNTIL=""
API_BASE="http://127.0.0.1:8000"
WORKSPACE_PATH="$REPO"
AUTHOR="claude#author-A"
FALLBACK_AUTHOR="codex#author-A"
EVOLUTION_LEVEL="0"
SELF_LOOP_MODE="1"
MAX_ROUNDS="3"
TASK_TIMEOUT_SECONDS="1800"
PRIMARY_DISABLE_SECONDS="3600"
PARTICIPANT_TIMEOUT_SECONDS="${AWE_PARTICIPANT_TIMEOUT_SECONDS:-3600}"
COMMAND_TIMEOUT_SECONDS="${AWE_COMMAND_TIMEOUT_SECONDS:-300}"
TEST_COMMAND="py -m pytest -q"
LINT_COMMAND="py -m ruff check ."
DRY_RUN="0"
AUTO_MERGE="1"
SANDBOX_MODE="1"
MERGE_TARGET_PATH=""
SANDBOX_WORKSPACE_PATH=""

declare -a REVIEWERS=("codex#review-B" "claude#review-C")
declare -a FALLBACK_REVIEWERS=("codex#review-B")
declare -a EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --until) UNTIL="${2:-}"; shift 2 ;;
    --api-base) API_BASE="${2:-}"; shift 2 ;;
    --workspace-path) WORKSPACE_PATH="${2:-}"; shift 2 ;;
    --author) AUTHOR="${2:-}"; shift 2 ;;
    --reviewer) REVIEWERS+=("${2:-}"); shift 2 ;;
    --fallback-author) FALLBACK_AUTHOR="${2:-}"; shift 2 ;;
    --fallback-reviewer) FALLBACK_REVIEWERS+=("${2:-}"); shift 2 ;;
    --evolution-level) EVOLUTION_LEVEL="${2:-}"; shift 2 ;;
    --self-loop-mode) SELF_LOOP_MODE="${2:-}"; shift 2 ;;
    --max-rounds) MAX_ROUNDS="${2:-}"; shift 2 ;;
    --task-timeout-seconds) TASK_TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --primary-disable-seconds) PRIMARY_DISABLE_SECONDS="${2:-}"; shift 2 ;;
    --participant-timeout-seconds) PARTICIPANT_TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --command-timeout-seconds) COMMAND_TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --test-command) TEST_COMMAND="${2:-}"; shift 2 ;;
    --lint-command) LINT_COMMAND="${2:-}"; shift 2 ;;
    --merge-target-path) MERGE_TARGET_PATH="${2:-}"; shift 2 ;;
    --sandbox-workspace-path) SANDBOX_WORKSPACE_PATH="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --no-auto-merge) AUTO_MERGE="0"; shift ;;
    --auto-merge) AUTO_MERGE="1"; shift ;;
    --no-sandbox) SANDBOX_MODE="0"; shift ;;
    --sandbox-mode) SANDBOX_MODE="${2:-}"; shift 2 ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$UNTIL" ]]; then
  echo "Missing required --until value (example: --until '2026-02-19 07:00')." >&2
  exit 2
fi

find_python() {
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  return 1
}

PYTHON_BIN="$(find_python)" || {
  echo "python not found (python/python3)." >&2
  exit 1
}

API_PID_FILE="$RUNTIME_DIR/api.pid"
API_STARTED_BY_SCRIPT="0"
if ! curl -fsS "$API_BASE/healthz" >/dev/null 2>&1; then
  "$REPO/scripts/start_api.sh"
  API_STARTED_BY_SCRIPT="1"
fi

API_PID=""
if [[ -f "$API_PID_FILE" ]]; then
  API_PID="$(head -n 1 "$API_PID_FILE" 2>/dev/null || true)"
fi

NIGHT_STDOUT="$OVERNIGHT_DIR/night-stdout.log"
NIGHT_STDERR="$OVERNIGHT_DIR/night-stderr.log"

export PYTHONPATH="$SRC"
export PYTHONUNBUFFERED="1"
export AWE_PARTICIPANT_TIMEOUT_SECONDS="$PARTICIPANT_TIMEOUT_SECONDS"
export AWE_COMMAND_TIMEOUT_SECONDS="$COMMAND_TIMEOUT_SECONDS"

cmd=(
  "$PYTHON_BIN" "$REPO/scripts/overnight_autoevolve.py"
  --api-base "$API_BASE"
  --until "$UNTIL"
  --workspace-path "$WORKSPACE_PATH"
  --author "$AUTHOR"
  --fallback-author "$FALLBACK_AUTHOR"
  --evolution-level "$EVOLUTION_LEVEL"
  --self-loop-mode "$SELF_LOOP_MODE"
  --max-rounds "$MAX_ROUNDS"
  --test-command "$TEST_COMMAND"
  --lint-command "$LINT_COMMAND"
  --task-timeout-seconds "$TASK_TIMEOUT_SECONDS"
  --lock-file "$LOCK_FILE"
  --primary-disable-seconds "$PRIMARY_DISABLE_SECONDS"
)

for reviewer in "${REVIEWERS[@]}"; do
  [[ -z "$reviewer" ]] && continue
  cmd+=(--reviewer "$reviewer")
done
for reviewer in "${FALLBACK_REVIEWERS[@]}"; do
  [[ -z "$reviewer" ]] && continue
  cmd+=(--fallback-reviewer "$reviewer")
done

if [[ "$AUTO_MERGE" == "1" ]]; then
  cmd+=(--auto-merge)
else
  cmd+=(--no-auto-merge)
fi
cmd+=(--sandbox-mode "$SANDBOX_MODE")
if [[ -n "$MERGE_TARGET_PATH" ]]; then
  cmd+=(--merge-target-path "$MERGE_TARGET_PATH")
fi
if [[ -n "$SANDBOX_WORKSPACE_PATH" ]]; then
  cmd+=(--sandbox-workspace-path "$SANDBOX_WORKSPACE_PATH")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  cmd+=(--dry-run)
fi
for arg in "${EXTRA_ARGS[@]}"; do
  cmd+=("$arg")
done

cd "$REPO"
nohup "${cmd[@]}" >"$NIGHT_STDOUT" 2>"$NIGHT_STDERR" &
NIGHT_PID="$!"

SESSION_PATH="$SESSIONS_DIR/session-$(date +%Y%m%d-%H%M%S).json"
"$PYTHON_BIN" - "$SESSION_PATH" "$UNTIL" "$API_BASE" "$API_PID" "$API_STARTED_BY_SCRIPT" "$NIGHT_PID" "$EVOLUTION_LEVEL" "$AUTO_MERGE" "$SANDBOX_MODE" <<'PY'
import json
import sys
from datetime import datetime

session_path = sys.argv[1]
payload = {
    "started_at": datetime.now().isoformat(timespec="seconds"),
    "until": sys.argv[2],
    "api_base": sys.argv[3],
    "api_pid": int(sys.argv[4] or 0),
    "api_started_by_script": sys.argv[5] == "1",
    "overnight_pid": int(sys.argv[6] or 0),
    "evolution_level": int(sys.argv[7] or 0),
    "auto_merge": sys.argv[8] == "1",
    "sandbox_mode": int(sys.argv[9] or 0),
}
with open(session_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
PY

echo "[launch] Overnight PID: $NIGHT_PID"
echo "[launch] Session file: $SESSION_PATH"
