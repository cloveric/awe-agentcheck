#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STARTER="$REPO/scripts/start_overnight_until_7.sh"
STOPPER="$REPO/scripts/stop_overnight.sh"
SESSIONS_DIR="$REPO/.agents/overnight/sessions"
mkdir -p "$SESSIONS_DIR"

UNTIL=""
CHECK_INTERVAL_SECONDS="20"
UNHEALTHY_THRESHOLD="2"
FORCE_INITIAL_RESTART="1"

declare -a FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --until)
      UNTIL="${2:-}"
      FORWARD_ARGS+=("$1" "$2")
      shift 2
      ;;
    --check-interval-seconds)
      CHECK_INTERVAL_SECONDS="${2:-}"
      shift 2
      ;;
    --unhealthy-threshold)
      UNHEALTHY_THRESHOLD="${2:-}"
      shift 2
      ;;
    --force-initial-restart)
      FORCE_INITIAL_RESTART="${2:-1}"
      shift 2
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$UNTIL" ]]; then
  echo "Missing required --until value." >&2
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

deadline_epoch="$("$PYTHON_BIN" - "$UNTIL" <<'PY'
import datetime
import sys
raw = sys.argv[1]
value = datetime.datetime.fromisoformat(raw.replace(" ", "T"))
print(int(value.timestamp()))
PY
)"

latest_session_file() {
  ls -1t "$SESSIONS_DIR"/session-*.json 2>/dev/null | head -n 1 || true
}

read_session_pid() {
  local file="$1"
  "$PYTHON_BIN" - "$file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(int(data.get("overnight_pid") or 0))
PY
}

if [[ "$FORCE_INITIAL_RESTART" == "1" ]]; then
  "$STOPPER" --all >/dev/null 2>&1 || true
fi

echo "[supervisor] starting initial overnight session until=$UNTIL"
"$STARTER" "${FORWARD_ARGS[@]}"

unhealthy_streak=0
while [[ "$(date +%s)" -lt "$deadline_epoch" ]]; do
  file="$(latest_session_file)"
  pid="0"
  if [[ -n "$file" && -f "$file" ]]; then
    pid="$(read_session_pid "$file")"
  fi
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" >/dev/null 2>&1; then
    unhealthy_streak=0
  else
    unhealthy_streak=$((unhealthy_streak + 1))
    echo "[supervisor] overnight process unhealthy streak=$unhealthy_streak"
    if [[ "$unhealthy_streak" -ge "$UNHEALTHY_THRESHOLD" ]]; then
      echo "[supervisor] restarting overnight stack"
      "$STOPPER" --all >/dev/null 2>&1 || true
      "$STARTER" "${FORWARD_ARGS[@]}"
      unhealthy_streak=0
    fi
  fi
  sleep "$CHECK_INTERVAL_SECONDS"
done

echo "[supervisor] deadline reached, exiting"
