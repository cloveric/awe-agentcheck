#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSIONS_DIR="$REPO/.agents/overnight/sessions"
LOCK_FILE="$REPO/.agents/overnight/overnight.lock"
SESSION_FILE=""
STOP_ALL="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-file)
      SESSION_FILE="${2:-}"
      shift 2
      ;;
    --all)
      STOP_ALL="1"
      shift
      ;;
    *)
      echo "[stop] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

stop_pid() {
  local pid="$1"
  [[ -z "$pid" || "$pid" == "0" ]] && return
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "[stop] stopped pid=$pid"
  else
    echo "[stop] pid=$pid not running"
  fi
}

if [[ "$STOP_ALL" == "1" ]]; then
  if command -v pgrep >/dev/null 2>&1; then
    while read -r pid; do
      [[ -z "$pid" ]] && continue
      stop_pid "$pid"
    done < <(pgrep -f "overnight_autoevolve.py" || true)
  fi
  for file in "$SESSIONS_DIR"/session-*.json; do
    [[ -f "$file" ]] || continue
    api_pid="$(python - "$file" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
if data.get("api_started_by_script"):
    print(int(data.get("api_pid") or 0))
PY
)"
    stop_pid "${api_pid:-0}"
  done
  rm -f "$LOCK_FILE"
  exit 0
fi

if [[ -z "$SESSION_FILE" ]]; then
  SESSION_FILE="$(ls -1t "$SESSIONS_DIR"/session-*.json 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "$SESSION_FILE" || ! -f "$SESSION_FILE" ]]; then
  echo "[stop] no session file found"
  exit 0
fi

overnight_pid="$(python - "$SESSION_FILE" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(int(data.get("overnight_pid") or 0))
PY
)"
api_payload="$(python - "$SESSION_FILE" <<'PY'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
flag = 1 if data.get("api_started_by_script") else 0
pid = int(data.get("api_pid") or 0)
print(f"{flag}:{pid}")
PY
)"

stop_pid "${overnight_pid:-0}"
api_started="${api_payload%%:*}"
api_pid="${api_payload##*:}"
if [[ "$api_started" == "1" ]]; then
  stop_pid "${api_pid:-0}"
fi
rm -f "$LOCK_FILE"
echo "[stop] cleaned lock file"
