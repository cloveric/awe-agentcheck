#!/usr/bin/env bash
set -euo pipefail

API_HOST="127.0.0.1"
PORT="8000"
START_TIMEOUT_SECONDS="20"
FORCE_RESTART="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      API_HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --start-timeout-seconds)
      START_TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --force-restart)
      FORCE_RESTART="1"
      shift
      ;;
    *)
      echo "[api] unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$REPO/.agents/runtime"
STDOUT_LOG="$RUNTIME_DIR/api-stdout.log"
STDERR_LOG="$RUNTIME_DIR/api-stderr.log"
PID_FILE="$RUNTIME_DIR/api.pid"
DB_PATH="$RUNTIME_DIR/awe-agentcheck.sqlite3"
mkdir -p "$RUNTIME_DIR"

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

has_listener() {
  local host="$1"
  local port="$2"
  local py="${3}"
  "$py" - "$host" "$port" <<'PY'
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.4)
try:
    s.connect((host, port))
except OSError:
    sys.exit(1)
finally:
    s.close()
sys.exit(0)
PY
}

PYTHON_BIN="$(find_python)" || {
  echo "[api] python not found (python/python3)." >&2
  exit 1
}

if [[ "$FORCE_RESTART" == "1" ]]; then
  "$REPO/scripts/stop_api.sh" --port "$PORT" >/dev/null 2>&1 || true
fi

if has_listener "$API_HOST" "$PORT" "$PYTHON_BIN"; then
  if [[ "$FORCE_RESTART" != "1" ]]; then
    echo "[api] already listening on $API_HOST:$PORT"
    exit 0
  fi
fi

export PYTHONPATH="$REPO/src"
export AWE_ARTIFACT_ROOT="$REPO/.agents"
if [[ -z "${AWE_ARCH_AUDIT_MODE:-}" ]]; then
  # Keep architecture gate strict unless operator explicitly overrides it.
  export AWE_ARCH_AUDIT_MODE="hard"
fi
if [[ -z "${AWE_DATABASE_URL:-}" ]]; then
  export AWE_DATABASE_URL="sqlite+pysqlite:///${DB_PATH//\\//}"
fi

cd "$REPO"
nohup "$PYTHON_BIN" -m uvicorn awe_agentcheck.main:app --host "$API_HOST" --port "$PORT" >"$STDOUT_LOG" 2>"$STDERR_LOG" &
PID="$!"
echo "$PID" >"$PID_FILE"

deadline=$((SECONDS + START_TIMEOUT_SECONDS))
healthy=0
while [[ "$SECONDS" -lt "$deadline" ]]; do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    break
  fi
  if curl -fsS "http://$API_HOST:$PORT/healthz" 2>/dev/null | grep -q '"status":"ok"'; then
    healthy=1
    break
  fi
  sleep 1
done

if [[ "$healthy" == "1" ]]; then
  echo "[api] started pid=$PID url=http://$API_HOST:$PORT"
  exit 0
fi

kill "$PID" >/dev/null 2>&1 || true
rm -f "$PID_FILE"
echo "[api] failed to start within timeout."
if [[ -f "$STDERR_LOG" ]]; then
  echo "--- stderr (tail) ---"
  tail -n 80 "$STDERR_LOG" || true
fi
if [[ -f "$STDOUT_LOG" ]]; then
  echo "--- stdout (tail) ---"
  tail -n 80 "$STDOUT_LOG" || true
fi
exit 1
