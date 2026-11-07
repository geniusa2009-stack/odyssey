# Unreal Backend Contract — `odyssey.game.v1`

The frozen protocol between the ODYSSEY Unreal Engine client and the backend. It is separate
from (and does not change) API v1. Base path: **`/api/game/v1`**.

* OpenAPI document: `GET /api/game/v1/openapi.json` (interactive docs at `/api/game/v1/docs`
  outside production). Normalised snapshot: `tests/fixtures/game/openapi-game-v1.json`.
* Recorded example payloads (real server output, validated against the models):
  `tests/fixtures/game/examples/` — see `index.json`.
* `python -m app.tools.game_contract --check` fails on *any* change to either; a contract
  change is a reviewed `--write` plus a note in this document.

## Compatibility rules

* Frozen: paths, methods, request fields and their meaning, response fields, event envelope,
  control frames, error envelope and public codes.
* Additive changes allowed within v1: new optional request fields with safe defaults, new
  response fields, new event types (clients ignore unknown types), new `reason` values (clients
  treat an unknown reason as its `code`), new actions, new content.
* Breaking changes require `odyssey.game.v2` at a new base path.
* Every request and response carries/accepts `protocol: "odyssey.game.v1"`; a request with
  another value is rejected (`VALIDATION_ERROR`).

## Authentication (session token seam)

`POST /sessions` returns `session_token` (`gst_…`) **once**. Send it on every session call as
`Authorization: Bearer <token>`; the WebSocket accepts the header (preferred) or `?token=`
(redacted from server logs by `QuerySecretFilter`). Only its
SHA-256 hash is stored; comparison is constant-time. Missing/wrong token → `403
PERMISSION_DENIED` (`invalid_session_token`); unknown session → `404 SESSION_NOT_FOUND`. There
are no accounts yet: the principal is `anonymous` (the `GameIdentityProvider` seam is where
real authentication plugs in), and the game API exposes **no** admin capability.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/features` | protocol, content version, actions (with params), event types, error codes, limits (no auth) |
| GET | `/catalog` | items, vehicle classes, infrastructure types (no auth; incidents are never in it) |
| POST | `/sessions` | create a campaign → `{session_token, bootstrap}` (201) |
| GET | `/sessions/{id}/bootstrap` | features + snapshot |
| GET | `/sessions/{id}/snapshot` | authoritative state as stored (does not advance the clock) |
| POST | `/sessions/{id}/restore` | **the** reconnect path: settle clock, snapshot, missed events or resync |
| POST | `/sessions/{id}/sync` | settle the server clock now |
| GET | `/sessions/{id}/events?after_seq=&limit=` | retained events page (≤ 500) |
| GET | `/sessions/{id}/checkpoints?limit=` | saves (newest first) |
| POST | `/sessions/{id}/commands` | **one semantic action** |
| POST | `/sessions/{id}/missions/{mission_id}/start` | start/replay an available mission |
| POST | `/sessions/{id}/phases/{phase_id}/start` | start a phase's next mission (locks → `phase_locked` / `mars_mission_locked`) |
| GET | `/sessions/{id}/rewind-points` | commands of the active timeline that can be rewound |
| POST | `/sessions/{id}/rewind` | fork the active timeline to just before a command |
| GET | `/sessions/{id}/capabilities` | capability graph with stages, evidence, certifications |
| GET | `/sessions/{id}/readiness/{profile_id}` | explicit gates (e.g. `mars_01_human_mission`) |
| GET | `/sessions/{id}/expansion-map` | Human Expansion Map nodes/edges |
| GET | `/sessions/{id}/insights/{insight_id}/why` | WHY? for an unlocked insight |
| GET | `/sessions/{id}/objects/{object_id}` | one known world object (on-demand detail) |
| GET | `/sessions/{id}/vehicles/{vehicle_id}` | shipyard/loadout view |
| POST | `/sessions/{id}/future-lens` | project ≤ 3 semantic candidates (known-only) |
| GET | `/sessions/{id}/black-box?timeline_id=&counterfactuals=` | causal node/edge graph |
| GET | `/sessions/{id}/engineering-profile?timeline_id=` | Engineering Profile (decisions) |
| GET | `/sessions/{id}/mission-dna?timeline_id=` | share-safe Mission DNA |
| WS | `/ws/sessions/{id}?token=&last_seq=` | realtime events ([GAME_REALTIME_PROTOCOL.md](GAME_REALTIME_PROTOCOL.md)) |

Ids in paths: sessions `gs_[a-z2-7]{26}`, timelines `gt_…`; semantic ids
`[A-Za-z0-9_.:-]{1,128}`. Rate limits are the server's `default` / `expensive` buckets
(Future Lens, Black Box and rewind are `expensive`).

## The semantic command

```json
POST /api/game/v1/sessions/gs_…/commands
Authorization: Bearer gst_…
{
  "protocol": "odyssey.game.v1",
  "command_id": "cmd-0001",              // client-generated, unique per session (trace id)
  "session_id": "gs_…",                  // must equal the path
  "timeline_id": "gt_…",                 // optional: STALE_STATE if not the active timeline
  "expected_state_version": 1,           // required: optimistic concurrency
  "idempotency_key": "idem-000001",      // required: 8–128 of [A-Za-z0-9_.:-]
  "action": "system.set_mode",           // a registered semantic action
  "actor": "commander",                  // only the commander is controllable in Phase 5
  "target": "earth.command.training.simulator",
  "params": {"mode": "off"},             // ≤ 8 string/int values, validated per action
  "client_timestamp": "2026-…",          // informational only, never trusted
  "anchor": "earth.command.training"     // optional world anchor (logged only)
}
```

Unknown fields are rejected (`VALIDATION_ERROR`): a client cannot send resource values,
completion, certifications, quantities, repairs or unlocks. The backend validates the action
against the current mission, campaign phase, timeline, world semantic state, target
existence/visibility/access, player location, parameters, requirements, resources, `once`
rules, capability/qualification state and module compatibility.

Response (`CommandResult`):

| Field | Meaning |
|---|---|
| `result` | `applied` or `no_change` (+ `reason`, e.g. `already_here`, `already_done`) |
| `state_version`, `prev_state_version` | `+1` when anything authoritative changed, else equal |
| `sim_tick`, `last_seq` | simulation tick after the turn; last event seq |
| `events` | the realtime events this turn produced (also pushed on the socket) |
| `context` | read-only answers (e.g. `npc.context_request`) |
| `mission_transition` | set when the mission ended: result, tier, capabilities progressed, certifications granted, next mission and its timeline (`snapshot_required`) |

Header `Idempotent-Replayed: true|false`. If an `Idempotency-Key` header is also sent it must
equal the body's key.

## Semantic actions (`GET /features` lists them with parameters)

| Action | Target | Notes |
|---|---|---|
| `world.zone_entered` | location | starts the mission clock once (missions with `start_on_zone_entered`) |
| `world.poi_discovered` | object | content-defined, usually `once` + discovery |
| `system.inspect` | object | sets `inspected:<id>`; may unlock insights/advance incidents |
| `system.set_mode` | object | `mode` from the object's interaction (`off`/`eco`/`nominal`/`boost`) |
| `power.reroute` | object | `direction` |
| `repair.perform` | object | requirements (diagnosed, spare available) + consumes the spare |
| `science.instrument_operate` | object | `operation` |
| `science.sample_collect` | object | sample item + discovery |
| `infrastructure.activate` / `.deactivate` | object | infrastructure power/mode |
| `vehicle.inspect` / `vehicle.dispatch` | object | `order` for dispatch |
| `cargo.transfer` / `inventory.move` | container (destination) | `item`, `quantity`, `from` |
| `module.install` | host | `slot`, `item`, `from` (compatibility checked) |
| `module.remove` | host | `slot`, `to` |
| `crew.assign_location` | location | e.g. the radiation shelter |
| `npc.context_request` | crew | read-only context (never mutates) |
| `mission.authorize` | gate object | completes an authorization mission when every requirement holds |
| `mission.clock_set` | — | `mode`: `PAUSED`, `REALTIME`, `ACCELERATED` |
| `checkpoint.save` | — | manual save, optional `label` |

Analysis and time-travel are endpoints rather than command types, because they do not mutate
the world: `future_lens.request` → `POST /future-lens`, `black_box.inspect` →
`GET /black-box`, `knowledge.inspect` → `GET /insights/{id}/why`, `rewind.execute` →
`POST /rewind` (versioned like a command). A vehicle loadout is `module.install` /
`module.remove` + `cargo.transfer` against the vehicle's slots and holds.

Never sent: walking, jumping, camera, suspension, doors, footsteps, button animations,
transforms. Interactions that are not available say why in the snapshot
(`interactions[].available/reason`).

## State versions

`state_version` is per game session and increases by exactly one on every authoritative
mutation (command, clock settlement that advanced time, mission start, rewind). Informational
events (`future_lens.ready`) do not change it. Always send the version of the snapshot your
decision was based on. On `409 STALE_STATE` (`error.state_version` holds the current value):
fetch `/snapshot` (or apply the events you missed), re-evaluate, retry with a **new**
`command_id` and `idempotency_key`.

## Errors

The shared envelope (identical to API v1):

```json
{"error": {"code": "DECISION_UNAVAILABLE", "reason": "not_at_location",
           "message": "not at location", "details": {"target": "…", "required_location": "…"},
           "request_id": "…", "recoverable": true, "state_version": 7}}
```

| Code | HTTP | Typical reasons |
|---|---|---|
| `VALIDATION_ERROR` | 422 | schema violations, unknown fields, bad ids |
| `INVALID_REQUEST` | 422 | `unknown_action`, `action_not_supported`, `invalid_parameter`, `unknown_parameter`, `actor_not_controllable`, `duplicate_command_id`, `idempotency_mismatch`, `session_mismatch`, `content_version_mismatch` |
| `DECISION_UNAVAILABLE` | 409 | `not_at_location`, `location_locked`, `target_locked`, `fault_not_diagnosed`, `required_spare_missing`, `spacecraft_not_inspection_ready`, `container_mass_limit_exceeded`, `vehicle_mass_limit_exceeded`, `insufficient_quantity`, `slot_occupied`, `module_category_incompatible`, `mount_incompatible`, `module_qualification_missing`, `clock_not_started`, `mission_not_available`, `mission_already_active`, `phase_locked`, `phase_content_not_authored`, `mars_mission_locked`, … |
| `STALE_STATE` | 409 | `stale_state`, `concurrent_modification`, `write_conflict` |
| `MISSION_COMPLETE` | 409 | `mission_not_active`, `mission_concluded` |
| `IDEMPOTENCY_KEY_REUSED` | 422 | same key, different body |
| `PERMISSION_DENIED` | 403 | `invalid_session_token` (missing, wrong or another session's token) |
| `SESSION_NOT_FOUND` / `NOT_FOUND` | 404 | `session_not_found`, `unknown_target`, `unknown_location`, `unknown_item`, `insight_not_unlocked`, `command_not_rewindable`, `timeline_not_found` |
| `RATE_LIMITED` | 429 | |
| `INTERNAL_ERROR` | 500 | never with a stack trace |

`mars_mission_locked` carries `details.lock_code = "MARS_MISSION_LOCKED"`,
`details.missing_gates` and `details.missing_capabilities` (example:
`examples/error_mars_locked.json`). Compatibility failures list every failed interface in
`details.incompatible`.

## Snapshot (`GameSnapshot`)

`session` (id, status, content id/version, state version, last seq), `timeline` (id, mission,
attempt, status, parent), `campaign` (phases with status/missing prerequisites, missions with
attempts/best tier, capabilities, certifications, discoveries, insights, persistent
infrastructure), `mission` (objectives, critical resources, alerts, authorization gate with
requirement status, outcome tier), `clock`, `world` (player location, locations with access,
known objects with status/power/mode/modules/interactions, containers with mass/volume vs
limits, active incidents, crew intents, recent cues), `discoveries`, `insights`, `resume`
(last seq, ws/events/restore paths, retention). Never: seeds, schedules, unstarted incidents,
unfired unforeseeable events, simulation/ledger ids, token hashes.

## Payload discipline

Bootstrap/restore once, then deltas (events). Detail endpoints on demand. Events pages ≤ 500.
Checkpoint lists ≤ 200. Snapshots are compact (< 64 kB with full Earth Command content). No
geometry, assets or presentation directives anywhere.

## Content versions

Every session records the content id/version/hash it was created with. A server only loads a
save whose version lies in `[manifest.compatible_from, manifest.content_version]`; otherwise
`422 INVALID_REQUEST` `content_version_mismatch` (non-recoverable). See
[SAVE_RESTORE.md](SAVE_RESTORE.md#content-versions).
