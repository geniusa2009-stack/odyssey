#!/usr/bin/env bash
# Runs the live contract harness against a real odyssey.game.v1 backend process.
#
#   ODYSSEY_BACKEND=../odyssey Tools/ProtocolCore/run_live.sh
#
# Starts the backend (uvicorn, SQLite file in a temporary directory, in-memory bus, mock AI — no
# secrets, no external services), builds the harness, runs the Earth Command scenario including a
# backend restart on the same database, then stops the backend. Read-only towards the backend repo.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BACKEND="$(cd "${ODYSSEY_BACKEND:-$ROOT/../odyssey}" && pwd)"
PORT="${ODYSSEY_LIVE_PORT:-8765}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/odyssey-live.XXXXXX")"
PIDFILE="$WORK/backend.pid"
PY="${ODYSSEY_PYTHON:-$BACKEND/.venv/bin/python}"

start_backend() {
  (
    cd "$WORK"
    ODYSSEY_ENVIRONMENT=development \
    ODYSSEY_DATABASE_URL="sqlite+aiosqlite:///$WORK/live.db" \
    ODYSSEY_AUTO_CREATE_SCHEMA=true \
    ODYSSEY_LOG_JSON=false ODYSSEY_LOG_LEVEL=WARNING \
    PYTHONPATH="$BACKEND" \
      nohup "$PY" -m uvicorn app.main:app --app-dir "$BACKEND" --host 127.0.0.1 --port "$PORT" \
      >>"$WORK/backend.log" 2>&1 &
    echo $! >"$PIDFILE"
  )
  for _ in $(seq 1 100); do
    curl -fsS "http://127.0.0.1:$PORT/api/v1/ready" >/dev/null 2>&1 && return 0
    sleep 0.2
  done
  echo "backend did not become ready; log:" >&2; tail -40 "$WORK/backend.log" >&2; return 1
}
stop_backend() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    for _ in $(seq 1 50); do kill -0 "$(cat "$PIDFILE")" 2>/dev/null || break; sleep 0.1; done
    rm -f "$PIDFILE"
  fi
}

case "${1:-run}" in
  _start) WORK="$2"; PIDFILE="$WORK/backend.pid"; start_backend; exit ;;
  _stop)  WORK="$2"; PIDFILE="$WORK/backend.pid"; stop_backend; exit ;;
esac

trap 'stop_backend' EXIT
make -s -C "$HERE" build/live_harness
start_backend
echo "backend $(git -C "$BACKEND" rev-parse --short HEAD) on :$PORT (work dir $WORK)"
set +e
"$HERE/build/live_harness" --port "$PORT" --root "$ROOT" \
  --stop-cmd "ODYSSEY_BACKEND='$BACKEND' ODYSSEY_LIVE_PORT=$PORT '$HERE/run_live.sh' _stop '$WORK'" \
  --start-cmd "ODYSSEY_BACKEND='$BACKEND' ODYSSEY_LIVE_PORT=$PORT '$HERE/run_live.sh' _start '$WORK'"
status=$?
set -e
if [[ $status -ne 0 ]]; then echo "--- backend log (tail) ---"; tail -60 "$WORK/backend.log"; fi
exit $status
