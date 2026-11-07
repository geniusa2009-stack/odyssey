# Game Backend Architecture (`odyssey.game.v1`)

Phase 5 adds the authoritative **mission/campaign brain** behind the ODYSSEY Unreal Engine 5.8
open-world client. It is a new, additive domain (`app/game/`) on top of the existing,
protected simulation. Nothing in the frozen API v1, the LUNA-01 scenario or the scientific
constants changed; the LUNA-01 regression hashes are identical (see the Phase 5 report).

```
Unreal client ──REST (semantic actions, reads)──▶ /api/game/v1  (mounted FastAPI sub-app)
      ▲                                               │
      └──────────WebSocket (odyssey.game.v1 events)───┤
                                                      ▼
                                   GameService  (single write path, one DB transaction)
                                     │  run_turn(): clock catch-up → plan → dry run → apply
                                     │             → finalize → react → mission end
                    ┌────────────────┼──────────────────────────────┐
                    ▼                ▼                              ▼
            pure game core     ServiceSimPort ──▶ MissionService   game tables
         (world, actions,       (ledger-recorded decisions,        (sessions, timelines,
          campaign, content,     clock advancement; v1 engine,      snapshots, checkpoints,
          inventory, progression) replay, Future Lens, Black Box)    commands, events)
```

## Two runtimes, one truth

| Unreal owns | Backend owns |
|---|---|
| movement, camera, animation, collision, local physics, rover driving, VFX, audio, locomotion, NPC pathfinding, Smart Objects, StateTrees, rendering, cinematics, spawn transforms | mission truth, simulation state, campaign progression, objectives, consequences, decisions, resources, scientific rules, world *semantic* state, incidents, Future Lens, Black Box, Rewind, Mission DNA, engineering profile, capabilities and qualification, inventories and cargo, infrastructure, discoveries, knowledge, mission history, Mars readiness, authoritative saves |

The backend never receives coordinates or per-frame data. The client sends **semantic
actions** (`world.zone_entered`, `system.set_mode`, `cargo.transfer`, `mission.authorize`, …);
the backend validates legality and decides results. See
[GAMEPLAY_BACKEND_BOUNDARIES.md](GAMEPLAY_BACKEND_BOUNDARIES.md).

## Package layout

| Package | Role | Pure? |
|---|---|---|
| `app/game/content/` | Versioned YAML content (`data/`), Pydantic schema, loader, cross-reference validator, decision rendering | yes |
| `app/game/world/` | `TimelineGameState` / `CampaignMeta` documents, conditions, effects, reactor (incidents, cues, unlocks), read views | yes |
| `app/game/actions/` | Semantic action registry (21 actions), planner (legality), rule errors | yes |
| `app/game/campaign/` | Phases, missions, prerequisites, readiness locks, completion/failure commits, persistent infrastructure | yes |
| `app/game/inventory/` | Containers, cargo mass/volume budgets, hardware modules and compatibility | yes |
| `app/game/progression/` | Capability graph, qualification stages, certifications, readiness gates | yes |
| `app/game/runtime/` | Server-authoritative mission clock (`SystemClock`, `FakeClock`) | yes |
| `app/game/realtime/` | Event derivation from public-state diffs; in-memory and Redis buses | derive: yes |
| `app/game/adapters/` | Future Lens and Black Box game adapters over the v1 safe read models | yes |
| `app/game/contracts/` | Frozen request/response and read shapes | yes |
| `app/game/application/` | `run_turn` (pure), `InMemoryGame` (tests/fuzz), `GameService` (DB), identity seam, reference sync, runtime | service: no |
| `app/game/persistence/` | SQLAlchemy models of the seven game tables | no |
| `app/game/api/` | REST routes, WebSocket, dependencies, the sub-app factory | no |

`tests/test_game_architecture.py` enforces the boundaries: the core imports no FastAPI,
SQLAlchemy, Redis, services or repositories; the simulation never imports the game; only
`app/game/api/` uses the web framework.

## Reuse instead of a second simulation

* **One engine.** Earth Command is a second scenario (`content/data/scenarios/earth-command.yaml`)
  for the *same* deterministic engine. Generation vs demand, battery reserve, priority load
  shedding, thermal coupling and maintenance are the engine's real equations. LUNA-01 uses the
  registry scenario `luna-01` v0.2.0 unchanged.
* **One ledger.** Every simulation decision a game action causes is recorded through
  `MissionService.decide` / `run_advance` (hash-chained, replayable, verifiable). Game sessions
  own simulation sessions marked `managed_by='game'`, which the v1 API cannot see
  (`session_not_found`) and v1 `GET /missions` does not list.
* **One Future Lens / Black Box / Rewind.** The adapters call the existing services and map
  the v1 hidden-information-safe read models onto semantic ids.
* **One error contract.** The game app installs the same handlers (`app/api/errors.py`) and
  uses the frozen public codes (`STALE_STATE`, `DECISION_UNAVAILABLE`, …) with specific reasons.
* **One idempotency store.** `app/services/idempotency` with scope `game_command`.

The only changes to pre-existing modules are additive seams: `MissionService(realtime=False,
game_access=True)`, `create_session_for(...)`, an optional `stop_when` observer on
`engine.advance` (observational: it can only end an advance early), `managed_by` columns,
extra structured-log fields and the shared error-handler module. API v1's OpenAPI snapshot and
contract fixtures are byte-identical (`python -m app.tools.openapi_snapshot --check`,
`python -m app.tools.contract_fixtures --check`).

## The turn (`app/game/application/turn.py`)

Every authoritative change is one **turn**, identical in production and in the in-memory
harness:

1. **Catch-up** — advance the simulation by the ticks the server clock owes (capped), stopping
   at the first tick where a clock-pausing incident starts; observe facts per tick; react.
2. **Plan** — pure validation of the command against mission, campaign, timeline, world state,
   target existence/visibility, location, parameters, requirements, resources, `once` rules,
   capabilities and module compatibility. Raises `GameRuleError(reason, kind)`.
3. **Dry run** — apply the plan's simulation decisions to *copies* of the state with the
   engine, finalize and react on copies. Any rejection aborts before an authoritative change.
4. **Apply** — record the decisions through the port (ledger), finalize the game-side
   consequences, react (incidents, cues, insight unlocks, facts).
5. **Mission end** — authorization completes an `authorization` mission; a concluded
   simulation completes or fails a `simulation_concluded` mission.

`GameService` then persists the timeline document, campaign meta, rewind anchor, command log,
checkpoints, transitions and realtime events, stores the idempotency record and commits — all
in one transaction. Events are published after commit (best effort; clients resume by `seq`).

## State ownership

* `TimelineGameState` (`game_timelines.doc`) — **timeline-local**: semantic location, object
  states, containers/cargo, installed modules, incidents, crew intents, cue cooldowns, flags,
  the clock, pending discoveries and evidence.
* `CampaignMeta` (`game_sessions.meta`) — **campaign-global**: phase/mission status and
  attempts, history, committed evidence and capability stages, certifications, committed
  discoveries, knowledge, carried cargo and persistent infrastructure records.

The rule set (what rewind may and may not touch) is in [SAVE_RESTORE.md](SAVE_RESTORE.md).

## Mission clock

Server-authoritative, lazily settled, no background task (`app/game/runtime/clock.py`):

* State in the timeline document: `mode` (`PAUSED`, `REALTIME`, `ACCELERATED`,
  `DECISION_PAUSED`), rate (`realtime_ticks_per_second`, `accelerated_multiplier`), an
  **anchor** (`anchor_wall_ms`, `anchor_tick`) and `max_catchup_ticks`.
* Whenever the session is processed under its row lock (any command, `/sync`, `/restore`,
  `/future-lens`), the due ticks are `floor(elapsed_s × rate) − (sim_tick − anchor_tick)`.
  Because the target is derived from the anchor and the *current* tick, processing twice at
  the same instant advances nothing (no double advancement; concurrent syncs are safe — tested
  on SQLite and PostgreSQL).
* At most `max_catchup_ticks` are applied at once; when more were owed the clock pauses with
  `unattended_limit` (the player left the game running).
* A pausing incident stops advancement at the tick it starts (`DECISION_PAUSED`). Mode changes
  re-anchor at (now, current tick). The client never sets time; `mission.clock_set` *requests*
  a mode.
* Determinism: the same recorded command times give the same result; tests inject `FakeClock`.

## Persistence (migration `0003`)

| Table | Holds |
|---|---|
| `game_profiles` | player identity seam (display name, principal) |
| `game_sessions` | one campaign: content id/version/hash, campaign meta, `state_version` (optimistic), `event_seq`, token hash, secret seed |
| `game_timelines` | one play-through of one mission → its simulation session/timeline, head document, parent/fork command |
| `game_state_snapshots` | pre-decision documents (rewind anchors) |
| `game_checkpoints` | saves (auto, mission transition, critical decision, incident resolved, manual) with doc + meta |
| `game_commands` | accepted commands (id, action, target, result, server time, decision ids) — the recorded timing and a duplicate-command guard |
| `game_events` | retained realtime envelopes for resume (bounded) |

Public ids are opaque (`gs_`, `gt_`, `ck_`, `gp_` + 128 random bits); world ids are stable,
human-readable semantic ids (`earth.command.engineering.power_bus_b`). No autoincrement id,
simulation session id, ledger decision id, seed or token hash is ever sent to a client
(`tests/test_game_hidden_information.py`).

## Concurrency, idempotency, atomicity

* `SELECT … FOR UPDATE` on the session row (PostgreSQL) **and** an application-managed version
  counter (`version_id_col` with `version_id_generator=False`): the service sets
  `state_version = prev + 1` exactly once per accepted mutation; every UPDATE is guarded by
  `WHERE state_version = <read>`. Losers get `STALE_STATE` (409, recoverable).
* `expected_state_version` is required on every command; `idempotency_key` is required and
  scoped by principal + session. A retry returns the stored response with
  `Idempotent-Replayed: true`; a key reused for a different body is `IDEMPOTENCY_KEY_REUSED`.
  A racing duplicate that loses the version race re-reads the idempotency record and returns
  the winner's response (tested). `command_id` is unique per session.
* Atomic examples: transfer + mass; module install + inventory removal; mission completion +
  evidence + certification + discoveries + infrastructure records + next mission + checkpoint;
  discovery + knowledge unlock; campaign transition + checkpoint. A rejection anywhere rolls
  the whole transaction back.

## Realtime

Events are *derived* from the before/after public state of a turn (`realtime/derive.py`), so
they can never contain anything a snapshot would not. Envelopes carry a gap-free per-session
`seq`, `state_version`/`prev_state_version`, simulation and server time. The WebSocket resumes
from `last_seq`, back-fills messages a bus lost, and asks for a resync when retention expired.
Redis pub/sub fans out across API processes. See [GAME_REALTIME_PROTOCOL.md](GAME_REALTIME_PROTOCOL.md).

## Observability

Structured `game_command` log lines carry `request_id`, `action_id` (command id),
`action_type`, `game_session_id`, `game_timeline_id`, `mission`, `game_state_version`,
`result`, `reason` and `duration_ms`. No tokens, payloads or seeds are logged. Simulation work
done for the game still feeds the existing `simulation_runs` table and `/api/v1/ops/stats`.

## Performance

`python -m app.tools.game_bench` measures every operation class with SQL statement counts.
Phase 5 run on PostgreSQL 16 + Redis 7 (2 vCPU container, in-process ASGI, no network; 30
calls each), median / p95 ms (statements): bootstrap 19 / 29 (6), snapshot 17 / 25 (6), semantic
action 34 / 44 (13), inventory transfer 34 / 41 (13), action recording a simulation decision
53 / 65 (22), restore 58 / 66 (20), events page 17 / 22 (3), Future Lens with two candidates and
four samples 167 / 326 (21), Black Box with counterfactuals 66 / 84 (9), WebSocket
command→event 33 / 37, reconnect + resume 15 / 18. These are local measurements, not
guarantees. No query grows with history: snapshots read the head documents, events and
checkpoints are paginated, retention trimming only issues statements when needed. A simulation
decision re-reads the simulation head inside `MissionService.decide` (the shared v1 core) —
four extra reads accepted for reuse. Payloads are bounded: snapshots are compact semantic
documents (< 64 kB, tested), histories are paginated, events are small deltas, and no assets
are ever in JSON.

## Related documents

[UNREAL_BACKEND_CONTRACT.md](UNREAL_BACKEND_CONTRACT.md) ·
[CAMPAIGN_MODEL.md](CAMPAIGN_MODEL.md) ·
[CAPABILITY_AND_CERTIFICATION.md](CAPABILITY_AND_CERTIFICATION.md) ·
[INVENTORY_CARGO_MODULES.md](INVENTORY_CARGO_MODULES.md) ·
[WORLD_SEMANTIC_STATE.md](WORLD_SEMANTIC_STATE.md) ·
[GAME_REALTIME_PROTOCOL.md](GAME_REALTIME_PROTOCOL.md) ·
[SAVE_RESTORE.md](SAVE_RESTORE.md) ·
[UNREAL_HANDOFF.md](UNREAL_HANDOFF.md) ·
[RUN_LOCAL_GAME_BACKEND.md](RUN_LOCAL_GAME_BACKEND.md)
