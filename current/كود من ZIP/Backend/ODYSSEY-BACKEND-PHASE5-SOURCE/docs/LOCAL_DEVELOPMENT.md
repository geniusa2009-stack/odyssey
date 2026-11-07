# Local Development

Everything runs locally for free. Nothing paid is required.

## Prerequisites

* Python ≥ 3.12 (developed on 3.13)
* [uv](https://docs.astral.sh/uv/) (dependency manager; the lockfile `uv.lock` is committed)
* Optional: Docker (PostgreSQL + Redis), or local PostgreSQL 16 / Redis 7

## 1. Zero-infrastructure mode (SQLite, in-memory bus, mock ORION)

```bash
uv sync                                   # installs runtime + dev dependencies from uv.lock
cp .env.example .env                      # optional; defaults already work
ODYSSEY_AUTO_CREATE_SCHEMA=true uv run uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs
```

Or use migrations instead of auto-create:

```bash
uv run alembic upgrade head               # creates ./odyssey-dev.db
uv run uvicorn app.main:app --reload
```

## 2. PostgreSQL + Redis with Docker Compose

```bash
docker compose up -d db redis             # infrastructure only
export ODYSSEY_DATABASE_URL=postgresql+asyncpg://odyssey:REDACTED_SECRET@localhost:5432/odyssey
export ODYSSEY_REDIS_URL=redis://localhost:6379/0
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Everything in containers (migration job runs first):

```bash
docker compose up --build                 # API on http://127.0.0.1:8000
```

The compose credentials are **local-development defaults**. Override `POSTGRES_PASSWORD`
etc. in a `.env` file for anything shared.

## 3. Without Docker

Database setup (PostgreSQL 16):

```sql
CREATE ROLE odyssey LOGIN PASSWORD 'choose-a-password';
CREATE DATABASE odyssey OWNER odyssey;
CREATE DATABASE odyssey_test OWNER odyssey;   -- for the test suite (it gets wiped)
```

Redis setup: `redis-server --port 6379` (any Redis ≥ 6). Redis is optional: without
`ODYSSEY_REDIS_URL` the API uses an in-process bus and cache. Use Redis when running more
than one API process so WebSocket updates reach every client.

## Commands

| Task | Command |
|---|---|
| Run API (dev) | `uv run uvicorn app.main:app --reload` |
| Run API (prod-like) | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers` |
| Apply migrations | `uv run alembic upgrade head` |
| Check models vs migrations | `uv run alembic check` |
| New migration | `uv run alembic revision --autogenerate -m "…"` |
| Tests | `uv run pytest` (see [TESTING.md](TESTING.md) for PostgreSQL/Redis variables) |
| Lint / format | `uv run ruff check app tests alembic` / `uv run ruff format app tests alembic` |
| Types | `uv run mypy app tests` |

There are no background workers: CPU-heavy engine work runs in a thread pool inside the API
process. A future wall-clock "mission timer" would be the first worker
([D2](USER_DECISIONS_REQUIRED.md#d2-mission-length-and-time-model)).

## Configuration

All settings are environment variables prefixed `ODYSSEY_`, documented in `.env.example`.
Secrets (`ODYSSEY_AI_API_KEY`, `ODYSSEY_NASA_API_KEY`, database passwords) are never committed,
are typed as `SecretStr`, and are redacted from logs.

## Free AI locally (optional)

```bash
ollama pull llama3.1
ODYSSEY_AI_PROVIDER=openai_compatible ODYSSEY_AI_BASE_URL=http://localhost:11434/v1 \
ODYSSEY_AI_MODEL=llama3.1 uv run uvicorn app.main:app
```

ORION validates every answer and falls back to the deterministic mock if the model invents
anything ([ORION.md](ORION.md)).

## Dependency pinning strategy

`pyproject.toml` declares compatible ranges (`>=x,<next-major`); `uv.lock` pins exact versions
with hashes and is what CI, Docker (`uv sync --frozen`) and developers install. Upgrade
deliberately with `uv lock --upgrade` and re-run the quality gates.
