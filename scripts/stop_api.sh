#!/usr/bin/env bash
set -euo pipefail

PORT="8000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    *)
      echo "[api] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$REPO/.agents/runtime/api.pid"

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" || "$pid" == "0" ]]; then
    return
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "[api] stopped pid=$pid"
  else
    echo "[api] pid=$pid not running"
  fi
}

if [[ -f "$PID_FILE" ]]; then
  pid="$(head -n 1 "$PID_FILE" 2>/dev/null || true)"
  stop_pid "$pid"
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1; then
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    stop_pid "$pid"
  done < <(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u)
else
  echo "[api] lsof not found; skipped listener PID cleanup on port $PORT"
fi
