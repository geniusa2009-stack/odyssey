# Run the Game Backend Locally (for Unreal development)

Everything is free and local. No paid or cloud service is required.

## Option A — zero infrastructure (SQLite, in-process realtime)

```bash
uv sync
export ODYSSEY_DATABASE_URL=sqlite+aiosqlite:///./odyssey-dev.db
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Good for a single Unreal editor instance talking to one API process.

## Option B — PostgreSQL + Redis (production-like)

```bash
docker compose up -d db redis                     # 1. database + 2. Redis
export ODYSSEY_DATABASE_URL=postgresql+asyncpg://odyssey:REDACTED_SECRET@localhost:5432/odyssey
export ODYSSEY_REDIS_URL=redis://localhost:6379/0
uv run alembic upgrade head                       # 3. migrations (0001 → 0003)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # 4. backend
```

Without Docker, use a local PostgreSQL 16 and `redis-server` (see
[LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md#3-without-docker)). Redis is needed when more than
one API process serves WebSockets (fan-out); otherwise optional.

## 5. Check readiness

```bash
curl -s http://127.0.0.1:8000/api/v1/ready
# {"status":"ready","checks":{"database":"ok","redis":"ok","scenarios":"ok"}}
curl -s http://127.0.0.1:8000/api/game/v1/features | head -c 300
```

Interactive docs: `http://127.0.0.1:8000/api/game/v1/docs` (disabled when
`ODYSSEY_ENVIRONMENT=production`).

## 6. Create or resume a game session

```bash
R=$(curl -s -X POST http://127.0.0.1:8000/api/game/v1/sessions \
      -H 'Content-Type: application/json' -d '{"display_name":"Commander"}')
TOKEN=$(echo "$R" | python -c "import sys,json;print(json.load(sys.stdin)['session_token'])")
SID=$(echo "$R" | python -c "import sys,json;print(json.load(sys.stdin)['bootstrap']['snapshot']['session']['id'])")

# a semantic action
curl -s -X POST http://127.0.0.1:8000/api/game/v1/sessions/$SID/commands \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"command_id\":\"cmd-1\",\"session_id\":\"$SID\",\"expected_state_version\":1,
       \"idempotency_key\":\"idem-000001\",\"action\":\"world.zone_entered\",
       \"target\":\"earth.command.engineering\"}"

# resume later (after an editor restart)
curl -s -X POST http://127.0.0.1:8000/api/game/v1/sessions/$SID/restore \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"last_seq":0}'
```

## 7. Connect the WebSocket

```
ws://127.0.0.1:8000/api/game/v1/ws/sessions/<SID>?token=<TOKEN>&last_seq=<last applied seq>
```

Quick check from a shell (the `websockets` package comes with `uvicorn[standard]`):

```bash
uv run python - "$SID" "$TOKEN" <<'EOF'
import asyncio, json, sys, websockets
async def main(sid, token):
    url = f"ws://127.0.0.1:8000/api/game/v1/ws/sessions/{sid}?token={token}&last_seq=0"
    async with websockets.connect(url) as ws:
        print(json.loads(await ws.recv()))          # RESUMED + backlog follows
asyncio.run(main(*sys.argv[1:]))
EOF
```

## Configuration that matters for the game

| Variable | Effect |
|---|---|
| `ODYSSEY_DATABASE_URL` | SQLite file or PostgreSQL |
| `ODYSSEY_REDIS_URL` | enables Redis fan-out of `odyssey.game.v1` events (and v1 realtime) |
| `ODYSSEY_CORS_ORIGINS` | only relevant for browser clients; also checked on WebSocket `Origin` |
| `ODYSSEY_RATE_LIMIT_PER_MINUTE` / `…_EXPENSIVE_…` | per-client limits (Future Lens, Black Box and rewind are "expensive") |
| `ODYSSEY_MAX_REQUEST_BYTES` | request body cap (commands are small) |
| `ODYSSEY_ENVIRONMENT=production` | hides interactive docs |

No secret is hard-coded; there are no game-specific secrets (session tokens are generated per
session and only their hash is stored).

## Tooling

| Task | Command |
|---|---|
| Game contract check (OpenAPI + examples) | `uv run python -m app.tools.game_contract --check` |
| Regenerate after a reviewed contract change | `uv run python -m app.tools.game_contract --write` |
| API v1 freeze check (must stay unchanged) | `uv run python -m app.tools.openapi_snapshot --check` and `uv run python -m app.tools.contract_fixtures --check` |
| Game latency benchmark | `uv run python -m app.tools.game_bench --database-url $ODYSSEY_DATABASE_URL --redis-url $ODYSSEY_REDIS_URL --repeat 30` |
| Game tests | `uv run pytest tests/test_game_*.py` (PostgreSQL/Redis variants via `ODYSSEY_TEST_POSTGRES_URL` / `ODYSSEY_TEST_REDIS_URL`, see [TESTING.md](TESTING.md)) |
| Longer fuzzing | `GAME_API_FUZZ_SEEDS=50 GAME_API_FUZZ_STEPS=150 uv run pytest tests/test_game_api_fuzz.py` |
