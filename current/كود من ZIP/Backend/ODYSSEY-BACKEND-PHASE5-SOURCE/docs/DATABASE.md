# Database

PostgreSQL 16 in production/compose; SQLite (aiosqlite) for zero-infrastructure development
and most tests. SQLAlchemy 2.0 async ORM; Alembic migrations (`alembic/versions/`). JSON
columns use `JSONB` on PostgreSQL and `JSON` elsewhere.

## What is stored, and why

| Table | Role | Mutability |
|---|---|---|
| `missions` | Mission catalogue (synced from packaged scenarios on startup) | Reference |
| `mission_scenarios` | Scenario definition **pinned by content hash** so old sessions replay with their own rules | Insert-only |
| `mission_sessions` | Session: scenario, seed, status, active timeline, Future Lens counter | Updated |
| `mission_participants` | Multiplayer participants and roles (pseudonymous handles) | Insert |
| `mission_timelines` | Timeline tree (parent, fork sequence/tick) + head pointer (tick, sequence, state hash, record hash), optimistic `version` | Head updated |
| `mission_timeline_branches` | Fork records: replaced decision, alternative inputs | Insert-only |
| `mission_decisions` | **Decision ledger**: the source of truth, hash-chained | **Append-only** (enforced) |
| `mission_snapshots` | Full state at initial / decision / advance / every 24 ticks / fork | Insert-only |
| `mission_events` | Event log per timeline (derivable by replay; stored for querying) | Insert-only |
| `mission_outcomes` | Outcome per concluded timeline | Insert-only |
| `mission_profiles` | Engineering profile per (timeline, weights version, head hash) | Insert-only |
| `mission_dna` | DNA per (timeline, head hash) | Insert-only |
| `science_evidence` | Evidence registry (synced from YAML) | Reference |
| `nasa_sources` | Data provenance (synced) | Reference |
| `simulation_runs` | Audit row for every engine invocation (kind, ticks, seed, duration, output hash) | Insert-only |
| `mission_realtime_events` | Realtime envelopes (`odyssey.realtime.v1`) of committed transitions, for reconnect/resume; the last 64 state versions per timeline are kept (Phase 4, migration `0002`) | Insert + pruned |
| `idempotency_records` | Stored response per (principal, endpoint, session, `Idempotency-Key`), written in the mutation's transaction (Phase 4, migration `0002`) | Insert-only |
| `game_profiles` | Game player identity seam (display name, principal) (Phase 5, migration `0003`) | Insert |
| `game_sessions` | One campaign (`odyssey.game.v1`): content id/version/hash, campaign meta document, application-managed `state_version`, realtime `event_seq`, token hash, secret seed | Updated (versioned) |
| `game_timelines` | One play-through of one mission: its simulation session/timeline, head timeline document, parent and fork command | Head updated |
| `game_state_snapshots` | Pre-decision timeline documents (rewind anchors) | Insert-only |
| `game_checkpoints` | Saves (auto, mission transition, critical decision, incident resolved, manual) with document + meta | Insert + auto pruned |
| `game_commands` | Accepted commands (unique per session) with server time and ledger decision ids | Insert-only |
| `game_events` | Retained `odyssey.game.v1` envelopes for resume (last 2,000 per session, unique `seq`) | Insert + pruned |

Phase 5 also adds a nullable `managed_by` column to `missions` and `mission_sessions`: rows owned
by the game backend (`'game'`) are invisible to API v1 (`GET /missions` filters them, session
loads answer `session_not_found`); existing rows keep `NULL`. Game timelines reuse the
simulation tables unchanged — every game decision is in the same append-only ledger. See
[GAME_BACKEND_ARCHITECTURE.md](GAME_BACKEND_ARCHITECTURE.md#persistence-migration-0003).

**Not every tick is persisted.** A 240-tick mission writes about 10 periodic snapshots plus one
per decision. Any tick can be reconstructed in ~0.1–0.2 s by replay, and `GET /verify` proves
that the stored head equals the replay.

## Integrity model

* **Hash chain**: `record_hash = SHA-256(prev_record_hash, id, timeline, sequence, tick, type,
  inputs, state_before_hash, state_after_hash)`. Reordering, editing or dropping a record breaks
  the chain (tested).
* **Head check**: reading the head state re-hashes the snapshot and compares it with the
  timeline's `head_state_hash`. A mismatch is a `500 state_hash_mismatch`, never silently
  served.
* **Append-only ledger**, enforced three ways:
  1. `DecisionRecord` is a frozen model;
  2. ORM `before_update` / `before_delete` listeners raise `LedgerImmutableError`;
  3. database triggers (`app/db/ledger_guard.py`, also in migration `0001`):
     PostgreSQL `trg_mission_decisions_append_only`, SQLite `trg_mission_decisions_no_update`
     / `_no_delete`. They reject raw SQL too.
* **Retention override (PostgreSQL only)**: a deliberate erasure job may delete ledger rows
  inside a transaction that first runs `SET LOCAL odyssey.allow_ledger_delete = 'on'`.
  Application code never sets it. UPDATE is never allowed. See
  [D13](USER_DECISIONS_REQUIRED.md#d13-student-data-retention-and-erasure).
* **Concurrency**: decision/advance lock the timeline row (`SELECT … FOR UPDATE` on
  PostgreSQL); the timeline's `version` column provides optimistic locking everywhere; clients
  can pass `expected_sequence`. Conflicts return `409` and nothing is written.
* **Transactions**: one service method = one transaction. Realtime messages are published
  only after commit.

## Indexes

Chosen for the access paths the service actually uses:

| Index / constraint | Serves |
|---|---|
| `uq_mission_decisions_timeline_id_sequence` | Ledger of a timeline in order; sequence uniqueness |
| `ix_mission_decisions_timeline_tick` | Decisions at/after a tick |
| `uq_mission_decisions_record_hash` | Chain integrity |
| `uq_mission_snapshots_timeline_id_tick_decisions_applied` | Latest snapshot of a timeline (`ORDER BY tick DESC, decisions_applied DESC`) |
| `uq_mission_events_timeline_id_event_id`, `ix_mission_events_timeline_tick`, `ix_mission_events_timeline_kind` | Idempotent event ids; timeline queries by tick/kind |
| `ix_mission_timelines_session_id`, `ix_mission_timelines_parent_timeline_id` | Timeline tree |
| `ix_mission_sessions_status_created` | Admin listings |
| `ix_simulation_runs_session_created` | Audit per session |
| `ix_mission_outcomes_outcome_code`, `ix_mission_dna_dna_code` | Future comparison/leaderboards |
| `uq_mission_realtime_events_timeline_id_state_version_seq`, `uq_mission_realtime_events_event_id` | Resume queries in event order; unique event ids |
| `uq_idempotency_records_principal_scope_session_key_idempotency_key` | One stored response per key; a concurrent duplicate fails the insert and replays |

Redundant single-column indexes were removed where a composite unique constraint already
leads with the same column.

## Migrations

```bash
uv run alembic upgrade head          # apply
uv run alembic check                 # fail if models and migrations differ
uv run alembic downgrade base        # roll back everything
uv run alembic upgrade head --sql    # print SQL without a database
uv run alembic revision --autogenerate -m "describe change"   # new migration
```

The database URL comes from `ODYSSEY_DATABASE_URL` (or `-x url=…`), never from `alembic.ini`.
Migrations `0001`, `0002` (Phase 4: `mission_realtime_events`, `idempotency_records`) and `0003`
(Phase 5: the seven `game_*` tables and the nullable `managed_by` columns; batch mode so it runs
on SQLite) are additive and verified in CI-style tests on SQLite **and** PostgreSQL: upgrade,
`check` (no drift), downgrade, re-upgrade, plus trigger behaviour.

For local development `ODYSSEY_AUTO_CREATE_SCHEMA=true` creates tables (with the same
triggers) without Alembic. Production should run migrations.
