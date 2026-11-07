# API

Base path: `/api/v1`. JSON over HTTP, plus one WebSocket. Interactive OpenAPI docs are served
at `/docs` (disabled when `ODYSSEY_ENVIRONMENT=production`); the schema is at `/openapi.json`
and a normalized, contract-tested copy is `tests/fixtures/contract/openapi-v1.json`.

| Document | For |
|---|---|
| [API_CONTRACT.md](API_CONTRACT.md) | The frontend-safe contract: read models, commands, versions, idempotency, errors, realtime, resume, Future Lens, Black Box, rewind, completion, limits |
| [API_FREEZE_V1.md](API_FREEZE_V1.md) | Which endpoints and contracts are FROZEN, PROVISIONAL or INTERNAL, and how the contract may change |
| [FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md) | How a client should use the API |

## Conventions

* **Strict input.** Unknown fields are rejected (`422 VALIDATION_ERROR`). Ids are
  pattern-checked. Bodies over 64 KiB → `413 PAYLOAD_TOO_LARGE`.
* **Errors** always use one envelope and never contain stack traces
  ([details](API_CONTRACT.md#errors)):

  ```json
  {"error": {"code": "INVALID_DECISION", "reason": "unknown_component",
             "message": "unknown component 'warp'", "details": {},
             "request_id": "3f2a…", "recoverable": false, "state_version": 3}}
  ```
* **Request ids.** Send `X-Request-ID` (8–64 chars of `[A-Za-z0-9_.-]`) or one is generated.
  It is echoed in the response and appears in every log line.
* **State versions.** Every timeline has a state version that increases by 1 per committed
  change. Commands carry `expected_state_version`; a stale one gets `409 STALE_STATE`
  ([details](API_CONTRACT.md#state-versioning-and-optimistic-concurrency)).
* **Idempotency.** `Idempotency-Key` on create-session and on every command endpoint
  ([details](API_CONTRACT.md#idempotency)).
* **Rate limits.** Per client IP, token bucket per minute: 120 for ordinary endpoints, 20 for
  expensive ones (marked ★). Exceeding them returns `429 RATE_LIMITED`.
* **Timelines.** Session endpoints act on the session's *active* timeline unless
  `timeline_id` is given (query parameter for GET, body field for POST).
* **Ticks.** `tick` = simulated hours elapsed (LUNA-01: 1 tick = 1 h).
* **Production.** Endpoints tagged `internal` return 404 and session views omit the seed when
  `ODYSSEY_ENVIRONMENT=production` (override: `ODYSSEY_INTERNAL_ENDPOINTS_ENABLED`).

## Endpoints

### Frozen application contract

| Method | Path | Purpose |
|---|---|---|
| GET | `/capabilities` | API info, error codes, capability flags |
| POST | `/mission-sessions` | `{mission_id?="luna-01", scenario_version?, seed?, participants?: [{handle, role}]}` → `201` session |
| GET | `/mission-sessions/{id}/bootstrap` | Versions, capabilities, scenario, session summary, snapshot |
| GET | `/mission-sessions/{id}/snapshot` | Authoritative current state of a timeline |
| GET | `/mission-sessions/{id}/decision-options` | Legal decisions (availability, reason, impact, parameters) and informational tools |
| POST | `/mission-sessions/{id}/decision-commands` | `{option_id, parameters?, expected_state_version, timeline_id?, participant_id?, metadata?}` → `201` |
| POST | `/mission-sessions/{id}/advance-commands` ★ | `{ticks (1…240), expected_state_version, timeline_id?, participant_id?}` |
| GET | `/mission-sessions/{id}/objectives` | Objective outlook |
| GET | `/mission-sessions/{id}/radiation-budget` | Radiation budget |
| GET | `/mission-sessions/{id}/resources/{resource_id}` | One resource: alert rules, recorded history |
| GET | `/mission-sessions/{id}/completion` | Outcome, objectives, blocked tiers, links to analyses |
| GET | `/mission-sessions/{id}/events` | Retained realtime events after `last_event_id` or `last_state_version` |
| GET | `/mission-sessions/{id}/history` ★ | Decisions, phases, mission events |
| POST | `/mission-sessions/{id}/future-lens/projections` ★ | What-if projections; never changes the mission |
| GET | `/mission-sessions/{id}/black-box/summary` ★ | Post-mortem: shortfalls, verified root decisions, causal chains |
| GET | `/mission-sessions/{id}/timelines` | Timeline tree |
| GET | `/mission-sessions/{id}/rewind-points` | Rewindable decisions |
| GET | `/mission-sessions/{id}/rewind-points/{decision_id}/preview` ★ | Fork preview |
| POST | `/mission-sessions/{id}/timeline-branches` ★ | Alternate timeline from a past decision |
| GET | `/mission-sessions/{id}/engineering-profile` ★ | Engineering Profile (provisional weights) |
| GET | `/mission-sessions/{id}/mission-dna/share` ★ | Share-safe Mission DNA |
| GET | `/science/claims`, `/science/claims/{id}` | Client-safe science evidence |
| WS | `/ws/mission-sessions/{id}` | Realtime `odyssey.realtime.v1` with resume ([details](API_CONTRACT.md#realtime)) |

### Provisional

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/ready` | Liveness; readiness of database, Redis (if configured), scenarios (`503` when not ready) |
| GET | `/missions`, `/missions/{mission_id}` | Missions with their pinned scenario versions |
| GET | `/missions/{mission_id}/metrics` | Metric catalogue (name, unit, label, severity mapping) |
| GET | `/mission-sessions/{id}` | Session, participants, timelines (`seed` null in production) |
| POST | `/mission-sessions/{id}/orion/explain` ★ | `{topic ("state_summary" \| "why" \| "decision_impact" \| "free_question"), question? (≤ 500), metric? (required for "why"), tick?, timeline_id?, participant_id?}` → grounded explanation ([ORION.md](ORION.md)) |
| GET | `/science/evidence`, `/science/evidence/{id}` | Raw evidence records |
| GET | `/nasa/sources` | Data sources with provenance (`is_real_data` distinguishes synthetic fixtures) |
| GET | `/nasa/space-weather/sep` ★ | `start`, `end` (≤ 31 days). DONKI SEP events with provenance; fixture fallback |

### Internal (engineering tools; 404 in production)

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/ops/stats` | | In-process engine run statistics (always 404 in production) |
| POST | `/mission-sessions/{id}/decisions` | `{decision, timeline_id?, participant_id?, expected_sequence?, expected_state_version?, metadata?}` | `201` ledger record, state hash and version, raw events, key metrics |
| POST | `/mission-sessions/{id}/advance` ★ | `{ticks, timeline_id?, participant_id?, expected_state_version?}` | From/to tick, phase, outcome, raw events (≤ 500), metrics |
| GET | `/mission-sessions/{id}/state` | `timeline_id?` | Raw `MissionState` (includes the seed), state hash and version |
| GET | `/mission-sessions/{id}/timeline` ★ | `timeline_id?, kinds?, from_tick?, to_tick?, limit?` | Raw ledger, ancestry, phase history, replayed raw events |
| GET | `/mission-sessions/{id}/verify` ★ | `timeline_id?` | Hash-chain check + full replay check against the stored head |
| POST | `/mission-sessions/{id}/future-lens` ★ | `{candidates (raw decisions), include_baseline?, horizon_ticks?, samples?, knowledge_policy?, explain?, …}` | Raw `FutureLensResult` ([FUTURE_LENS.md](FUTURE_LENS.md)) |
| GET | `/mission-sessions/{id}/black-box` ★ | `timeline_id?, counterfactuals?` | Raw `BlackBoxReport` ([BLACK_BOX.md](BLACK_BOX.md)) |
| GET | `/mission-sessions/{id}/trace` ★ | `metric, tick?, timeline_id?` | Raw root-cause trace |
| POST | `/mission-sessions/{id}/rewind` ★ | `{decision_id, alternative? (raw), continue_ticks?, activate?, label?, …}` | `201` child timeline |
| GET | `/mission-sessions/{id}/profile` ★ | `timeline_id?` | Raw Engineering Profile |
| GET | `/mission-sessions/{id}/mission-dna` ★ | `timeline_id?` | Raw `{version, code, genes}` |

### Outcome codes (LUNA-01)

| Code | Tier | When (v0.2.0) |
|---|---|---|
| `mission_complete_exceptional` | exceptional | primary + safety + stability + efficiency + science objectives all achieved (new in v0.2.0) |
| `mission_complete` | success | primary + safety + stability |
| `mission_complete_partial` | partial | primary only |
| `mission_failed` | mission failed | a primary objective failed (the crew may be safe), or the catch-all |
| `mission_failed_crew_loss` | critical failure | crew loss (ends the mission immediately) |

Codes are unchanged from v0.1.0 except the new exceptional one. Objective events carry their
`category` and the outcome event its `tier` (v0.2.0 scenarios only; v0.1.0 events are
byte-identical). Mission DNA tags: `MX`, `MC`, `MP`, `MF`, `CL` (`IP` while in progress).

## Engine decisions

The frozen contract addresses decisions by `option_id` (`GET .../decision-options`). Each maps to
one engine decision; the internal endpoints take the engine form directly (a discriminated
union on `type`):

| `type` | Fields | `option_id` | Effect |
|---|---|---|---|
| `set_subsystem_mode` | `subsystem`, `mode` (`off`/`eco`/`nominal`/`boost`, per subsystem) | `set_subsystem_mode:{subsystem}:{mode}` | Demand and output multiplier |
| `set_thermal_setpoint` | `target_c` (scenario range, LUNA-01 10–26) | `set_thermal_setpoint` + `{"target_c"}` | Heater regulation target |
| `set_ration_level` | `level` (≥ scenario minimum, LUNA-01 0.5) | `set_ration_level` + `{"level"}` | Food use vs crew health |
| `schedule_maintenance` | `component` | `schedule_maintenance:{component}` | Offline for N ticks, then health restored |
| `set_crew_location` | `location` (`habitat`/`shelter`) | `set_crew_location:{location}` | Radiation shielding vs science |
| `start_science_activity` | `opportunity_id` | `start_science_activity:{opportunity}` | Runs habitat science (power + crew) |
| `stop_science_activity` | | `stop_science_activity` | |
| `rover_command` | `action` (`traverse`/`recall`/`transfer_energy`/`stow`/`unstow`), `opportunity_id?` | `rover_command:{action}`, `rover_command:traverse:{opportunity}` | Rover operations |
| `clean_solar_array` | `crew_id` | `clean_solar_array:{crew_id}` | EVA: radiation exposure + fatigue, restores array |

A decision that does not exist or has bad parameters → `422 INVALID_DECISION`; one that exists
but is impossible now → `409 DECISION_UNAVAILABLE` with the engine's reason. Nothing is recorded.

## Example session (frozen contract)

```bash
API=http://127.0.0.1:8000/api/v1
SID=$(curl -s -XPOST $API/mission-sessions -H 'content-type: application/json' \
      -H 'Idempotency-Key: demo-create-0001' -d '{"seed": 42}' | jq -r .id)
V=$(curl -s $API/mission-sessions/$SID/bootstrap | jq .snapshot.state_version)
V=$(curl -s -XPOST $API/mission-sessions/$SID/advance-commands -H 'content-type: application/json' \
      -d "{\"ticks\": 20, \"expected_state_version\": $V}" | jq .state_version)
curl -s -XPOST $API/mission-sessions/$SID/decision-commands -H 'content-type: application/json' \
     -d "{\"option_id\": \"start_science_activity:regolith_survey\", \"expected_state_version\": $V}"
curl -s -XPOST $API/mission-sessions/$SID/future-lens/projections -H 'content-type: application/json' \
     -d '{"candidates": [{"label": "eco comms", "decisions": [{"option_id": "set_subsystem_mode:comms:eco"}]}]}'
curl -s $API/mission-sessions/$SID/objectives
```
