# Architecture

## Principles

1. **The deterministic engine owns truth.** Everything else (API, database, ORION, realtime,
   analysis) reads from it or records its outputs. Nothing writes around it.
2. **The simulation is a standalone domain package.** `app/simulation/` imports only the
   standard library, Pydantic and PyYAML. A test (`tests/test_architecture.py`) fails the
   build if it imports FastAPI, SQLAlchemy, Redis, httpx, AI or any outer layer.
3. **History, not just state.** A mission is `initial state + decision ledger + engine`.
   Snapshots are a read cache, and any state can be rebuilt and verified by replay.
4. **Data-driven scenarios.** Phases, events, alerts, objectives, outcomes and every balancing
   constant are YAML validated by a schema; designers do not touch engine code.
5. **Zero-cost by default.** SQLite, in-memory bus and a mock AI provider make the API boot
   with no infrastructure. PostgreSQL, Redis and real AI are optional upgrades.

## Layout

```
app/
  main.py                 FastAPI app factory: middleware, error handlers, lifespan
  core/                   settings (env), error taxonomy, structured logging
  api/                    HTTP + WebSocket adapters, DI container, security middleware
    v1/routes.py          REST endpoints (thin: validate → service → schema)
    v1/ws.py              WebSocket fan-out + resume (read-only; writes go through REST)
  schemas/api.py          request/response contracts (Phase 1–3 endpoints)
  schemas/commands.py     frozen command contracts (decision, advance, Future Lens, branch)
  read_models/            frontend-safe projections of simulation truth (Phase 4)
  services/               orchestration: transactions, engine registry, permissions,
                          reference-data sync; mission_service.py (orchestrator),
                          contract_service.py (frozen contract), idempotency.py
  realtime/contract.py    frozen realtime envelope odyssey.realtime.v1
  tools/                  OpenAPI snapshot, contract fixtures, API benchmark
  repositories/           query helpers (ledger resolution, head state)
  db/                     ORM models, session factory, ledger append-only guard
  simulation/             ── standalone domain package ──
    canonical.py          canonical JSON + hashing
    domain/               state, decisions, events, enums
    engine/               engine, RNG, metrics, dependency graph, conditions, end-of-tick logic
    systems/              environment, power, thermal, life support, comms/science,
                          rover, crew, degradation (one pure-ish function per system)
    events/               declarative event processor
    scenarios/            schema, loader, data/luna-01.yaml
    replay/               ledger (hash chain), replay, timelines/forks
    analysis/             reconstruct, root cause, Black Box, Future Lens, profile, DNA
  ai/                     ORION: context builder, providers (mock, OpenAI-compatible), service
  nasa/                   provider interfaces, fixtures, cache, provenance models
  science/                evidence registry (+ data/evidence.yaml)
  realtime/               event bus (in-memory / Redis pub/sub)
  telemetry/              in-process run statistics
alembic/                  migrations
tests/                    unit, property, integration, API, perf
```

(`missions/` from the spec's suggested layout is represented by `simulation/scenarios/` +
the `missions` table; a separate package would have been empty.)

## Data flow: a player decision

```
Player decision (HTTP POST /mission-sessions/{id}/decision-commands)
 → API          routes.py: path/body validated by Pydantic (option_id + parameters),
                body-size limit, rate limit, request id, Idempotency-Key (stored response?)
 → Validation   ContractService: option_id → engine decision (INVALID_DECISION if unknown);
                MissionService: load session + timeline (row lock), permission policy,
                optimistic concurrency (expected_state_version), head integrity (hash check)
 → Simulation   SimulationEngine.apply_decision on a *copy* of the head state; scenario
   Engine       rules validate it (DecisionRejectedError → 409 DECISION_UNAVAILABLE)
 → State        new state + provenance (which decision set which value) + events
   Transition
 → Decision     DecisionRecord: id, session, timeline, sequence, tick, type, inputs, phase,
   Ledger       affected systems, state before/after (+ hashes), prev hash → record hash
 → Persistence  one transaction: ledger row, events, snapshot, timeline head (version + 1),
                run audit row, realtime envelopes (odyssey.realtime.v1), idempotency row
                (commit; version-checked timeline row)
 → Realtime     queued messages published *after* commit → WebSocket subscribers
   Update
```

Advancing time follows the same path with `engine.advance` (run in a worker thread), periodic
snapshots, and an outcome row when the mission concludes.

## Data flow: ORION

```
Simulation truth (head state, effective ledger, root-cause trace)
 → Structured mission context   frozen facts, each with a stable id
 → Science evidence             matching evidence items added as citable facts
 → ORION                        provider produces JSON segments with citations
 → Grounding validation         unknown citations / unsupported numbers → rejected
 → Explanation                  (fallback: deterministic mock answer, flagged)
```

ORION has no import path to the engine's write methods, the database or the services (tested).
**AI never sits between the player decision and simulation truth.**

## Analysis on top of history

| Feature | Input | Mechanism |
|---|---|---|
| Timeline / Black Box | effective ledger | deterministic replay with hash verification at every decision |
| Root cause / Mission Trace | replayed history | dependency-graph walk + provenance + counterfactual replay |
| Future Lens | head state | isolated copies, derived seeds, unforeseeable events hidden |
| Rewind | effective ledger | fork = replay to the decision, new child timeline, parent untouched |
| Profile / Mission DNA | replayed history | pure functions; weights/genes versioned |

## Application layer (Phase 4)

```
client ──► routes.py ──► ContractService (extends MissionService, the orchestrator)
                           │  load + lock timeline, check expected_state_version,
                           │  idempotency lookup, permission policy
                           ├─► SimulationEngine (truth: decisions, advance, replay, analyses)
                           ├─► ledger / snapshots / events / realtime log / idempotency row
                           │   (one transaction; timeline version +1)
                           ├─► commit, then publish realtime envelopes (EventBus)
                           └─► read_models.* (projection of engine + head state) ──► response
```

* **The orchestrator never re-implements simulation logic**: the engine computes every new
  state; the orchestrator persists, versions, publishes and projects.
* **Read models** (`app/read_models/`) are pure functions of `(engine, state)` (plus recorded
  states for trends and history). They hold no state, never mutate the simulation state
  (tested) and are tested to be identical with or without hidden future events.
* **Commands** reference decisions by `option_id`; `read_models/decisions.py` maps an option to
  an engine decision and asks the engine whether it is available (on a private copy).
* **Versioning**: `mission_timelines.version` (SQLAlchemy `version_id_col`) is the public state
  version.

## Game backend (Phase 5)

The Unreal open-world client talks to a separately versioned sub-application mounted at
`/api/game/v1` (`odyssey.game.v1`, own OpenAPI document and snapshot). It is a game layer on
top of the same engine, ledger, Future Lens, Black Box and rewind — see
[GAME_BACKEND_ARCHITECTURE.md](GAME_BACKEND_ARCHITECTURE.md) and
[UNREAL_BACKEND_CONTRACT.md](UNREAL_BACKEND_CONTRACT.md). API v1 is unchanged.

## Persistence strategy

The ledger is the source of truth and is append-only at three levels: frozen Pydantic records,
an ORM guard, and database triggers. Snapshots (initial, every decision, every advance, every 24
ticks) make reads O(1). Events are stored for querying but are derivable. Details:
[DATABASE.md](DATABASE.md).

## Realtime and multiplayer readiness

* `EventBus` protocol with an in-memory and a Redis pub/sub implementation. Redis fans out
  across API processes.
* Messages are `odyssey.realtime.v1` envelopes (`app/realtime/contract.py`): one ordered group
  per committed transition, sharing a `state_version`, with `prev_state_version` for gap
  detection. They are written to `mission_realtime_events` in the same transaction as the
  change and published only after commit, so clients resume from their last event id or
  re-fetch the snapshot ([API_CONTRACT.md](API_CONTRACT.md#realtime)).
* Sessions have many `mission_participants` with roles. Every write passes through
  `MissionService._authorize(participant, action, decision_type)` with a pluggable
  `PermissionPolicy`. Concurrent writers are serialised by row locks (PostgreSQL),
  optimistic `version` columns, and `expected_state_version` / `expected_sequence`.

## Error handling and security

* Domain errors map to a fixed taxonomy (`app/core/errors.py`) and a single JSON shape:
  `{"error": {"code", "reason", "message", "details", "request_id", "recoverable",
  "state_version"}}` with a frozen list of public codes. Unhandled exceptions return a generic
  500. Stack traces never leave the server.
* In production the raw engine endpoints (tag `internal`) answer 404 and session views omit the
  seed (`Settings.internals_exposed`), so a client cannot obtain the information needed to
  compute hidden future events; omniscient Future Lens is off unless explicitly enabled.
* Security defaults: strict request schemas (`extra="forbid"`), path patterns, 64 KiB body
  limit, per-client token-bucket rate limits (separate bucket for expensive endpoints),
  CORS off unless configured, security headers, no secrets in code (typed settings with
  `SecretStr`, redacted logs), parameterised SQL only (ORM).
* Authentication is not implemented by design. See
  [D9](USER_DECISIONS_REQUIRED.md#d9-authentication-and-identity) for the integration point.

## Authentication seam

Authentication is deliberately not built ([D9](USER_DECISIONS_REQUIRED.md#d9-authentication-and-identity)).
Phase 2 verified (`tests/test_auth_seam.py`) that its absence **cannot corrupt the simulation
architecture**. An unauthenticated caller holding a session id can make *valid moves* in that
session (vandalism), but cannot:

* reach another session's timelines, participants or decisions (every lookup is scoped by
  session id: 404);
* act as a participant of another session (`unknown_participant`) or bypass a role policy (403);
* write anything the engine has not validated, edit the ledger (append-only at ORM and database
  level), or desynchronise the stored head from its replay (`GET /verify` stays green);
* change the mission through Future Lens or ORION (read-only by construction and by test).

**Where auth plugs in.** Every state-changing or policy-relevant call already passes through
one method:

```
MissionService._authorize(session_id, participant_id, action, detail)
  action: DECIDE (detail = decision type) · ADVANCE · REWIND (detail = alternative type)
          FUTURE_LENS (detail = knowledge policy) · ORION (detail = topic)
```

A future auth layer adds a FastAPI dependency that turns a credential into a participant id
(instead of trusting the `participant_id` field in the body) and passes it here. Nothing in the
engine, ledger or analysis changes. Phase 4 routes every endpoint through one identity
dependency (`app/api/deps.py::get_principal`, "anonymous" until auth exists); idempotency keys
are scoped by it. Read endpoints (snapshot, timeline, Black Box, profile,
DNA) are not yet policy-checked; they need a `VIEW` check once identities exist.

## Observability

JSON logs carry `request_id`, `mission_session_id`, `timeline_id`, `simulation_run_id`,
`state_version`, `decision_id`, `scenario_version`, `event_id`, `event_type`, `error_code`,
`idempotent_replay` and `duration_ms`. Keys that look like secrets are redacted. Every
engine invocation writes a `simulation_runs` audit row and feeds in-process statistics
(`GET /api/v1/ops/stats`, disabled in production). `/health` is liveness, `/ready` checks the
database, Redis (if configured) and scenario loading.
