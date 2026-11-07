# API Freeze v1

What a frontend may depend on. Each part of the `/api/v1` surface is marked:

* **FROZEN** — stable for frontend integration. Within v1 it only changes additively (new
  optional fields, new endpoints, new `reason` values, new event `kind`s inside `MISSION_EVENT`).
  Removing or renaming anything, changing a type or a meaning, or adding a required request
  field needs a new major version (`/api/v2`).
* **PROVISIONAL** — usable, but the shape may still change in v1 with notice in this document.
* **INTERNAL** — engineering, debugging and teacher tooling. Not for clients. Exposes raw engine
  objects; **disabled (404) when `ODYSSEY_ENVIRONMENT=production`** unless
  `ODYSSEY_INTERNAL_ENDPOINTS_ENABLED=true`.

The frontend should only depend on FROZEN contracts.

## Endpoints

| Status | Method | Path (`/api/v1` +) | Purpose |
|---|---|---|---|
| FROZEN | GET | `/capabilities` | API info, error codes, capability flags |
| FROZEN | POST | `/mission-sessions` | Create a session (idempotent with `Idempotency-Key`) |
| FROZEN | GET | `/mission-sessions/{id}/bootstrap` | Everything to start or resume |
| FROZEN | GET | `/mission-sessions/{id}/snapshot` | Authoritative current state |
| FROZEN | GET | `/mission-sessions/{id}/decision-options` | Legal decisions and informational tools |
| FROZEN | POST | `/mission-sessions/{id}/decision-commands` | Submit a decision (versioned, idempotent) |
| FROZEN | POST | `/mission-sessions/{id}/advance-commands` | Advance time (versioned, idempotent) |
| FROZEN | GET | `/mission-sessions/{id}/objectives` | Objective outlook |
| FROZEN | GET | `/mission-sessions/{id}/radiation-budget` | Radiation budget |
| FROZEN | GET | `/mission-sessions/{id}/resources/{resource_id}` | One resource with alert rules and recorded history |
| FROZEN | GET | `/mission-sessions/{id}/completion` | Mission completion |
| FROZEN | GET | `/mission-sessions/{id}/events` | Retained realtime events after a cursor (resume) |
| FROZEN | GET | `/mission-sessions/{id}/history` | Decisions, phases and mission events of a timeline |
| FROZEN | POST | `/mission-sessions/{id}/future-lens/projections` | Future Lens |
| FROZEN | GET | `/mission-sessions/{id}/black-box/summary` | Black Box |
| FROZEN | GET | `/mission-sessions/{id}/timelines` | Timeline tree |
| FROZEN | GET | `/mission-sessions/{id}/rewind-points` | Rewindable decisions |
| FROZEN | GET | `/mission-sessions/{id}/rewind-points/{decision_id}/preview` | Fork preview |
| FROZEN | POST | `/mission-sessions/{id}/timeline-branches` | Create an alternate timeline (idempotent) |
| FROZEN | GET | `/mission-sessions/{id}/engineering-profile` | Engineering Profile |
| FROZEN | GET | `/mission-sessions/{id}/mission-dna/share` | Share-safe Mission DNA |
| FROZEN | GET | `/science/claims`, `/science/claims/{id}` | Science evidence (client-safe) |
| FROZEN | WS | `/ws/mission-sessions/{id}` | Realtime `odyssey.realtime.v1`, with resume |
| PROVISIONAL | POST | `/mission-sessions/{id}/orion/explain` | ORION explanation (ORION's response shape is not redesigned in Phase 4) |
| PROVISIONAL | GET | `/mission-sessions/{id}` | Session view (superseded for clients by the bootstrap; `seed` is null in production) |
| PROVISIONAL | GET | `/missions`, `/missions/{id}`, `/missions/{id}/metrics` | Mission catalogue and metric catalogue |
| PROVISIONAL | GET | `/science/evidence`, `/science/evidence/{id}` | Raw evidence records (clients use `/science/claims`) |
| PROVISIONAL | GET | `/nasa/sources`, `/nasa/space-weather/sep` | NASA data provenance and DONKI SEP events |
| PROVISIONAL | GET | `/health`, `/ready` | Liveness and readiness |
| INTERNAL | GET | `/mission-sessions/{id}/state` | Raw `MissionState` (includes the seed) |
| INTERNAL | GET | `/mission-sessions/{id}/timeline` | Raw ledger and raw engine events |
| INTERNAL | GET | `/mission-sessions/{id}/verify` | Ledger hash chain and replay check |
| INTERNAL | POST | `/mission-sessions/{id}/decisions` | Legacy decision command (raw engine decision union) |
| INTERNAL | POST | `/mission-sessions/{id}/advance` | Legacy advance command |
| INTERNAL | POST | `/mission-sessions/{id}/rewind` | Legacy rewind command |
| INTERNAL | POST | `/mission-sessions/{id}/future-lens` | Raw Future Lens result (names excluded hidden events) |
| INTERNAL | GET | `/mission-sessions/{id}/black-box` | Raw Black Box report (graph nodes and edges) |
| INTERNAL | GET | `/mission-sessions/{id}/trace` | Raw root-cause trace of any metric |
| INTERNAL | GET | `/mission-sessions/{id}/profile` | Raw Engineering Profile |
| INTERNAL | GET | `/mission-sessions/{id}/mission-dna` | Raw Mission DNA |
| INTERNAL | GET | `/ops/stats` | Engine run statistics (always 404 in production) |

In OpenAPI the frozen endpoints carry tags starting with `contract-`, internal ones the tag
`internal`.

## Cross-cutting contracts

| Status | Contract | Reference |
|---|---|---|
| FROZEN | Error envelope `{error: {code, reason, message, details, request_id, recoverable, state_version}}` and the list of public `code`s with their HTTP status and `recoverable` flag | [API_CONTRACT.md#errors](API_CONTRACT.md#errors) |
| FROZEN | State versions and `409 STALE_STATE` (commands require `expected_state_version`) | [API_CONTRACT.md#state-versioning-and-optimistic-concurrency](API_CONTRACT.md#state-versioning-and-optimistic-concurrency) |
| FROZEN | `Idempotency-Key` semantics and the `Idempotent-Replayed` header | [API_CONTRACT.md#idempotency](API_CONTRACT.md#idempotency) |
| FROZEN | Realtime envelope, event types, ordering rules, control frames, resume cursors and resync reasons | [API_CONTRACT.md#realtime](API_CONTRACT.md#realtime) |
| FROZEN | `option_id` grammar and the decision command mapping | [API_CONTRACT.md#decisions](API_CONTRACT.md#decisions) |
| FROZEN | Outcome codes and tiers; objective pillars | [API_CONTRACT.md#mission-completion](API_CONTRACT.md#mission-completion) |
| FROZEN | Phase visibility: future phases are withheld (`null`, `*_withheld: true`) unless announced by the mission plan (D25, resolved) | [API_CONTRACT.md#phase-visibility](API_CONTRACT.md#phase-visibility) |
| FROZEN | Versions: API (`v1`), read model (`1`), realtime contract, scenario version — separate concepts | [API_CONTRACT.md#versions](API_CONTRACT.md#versions) |
| FROZEN | `X-Request-ID` echo; limits (body size, ticks, Future Lens bounds) | [API_CONTRACT.md#limits](API_CONTRACT.md#limits) |
| PROVISIONAL | Rate-limit numbers (120 / 20 per minute per IP) | configuration |
| PROVISIONAL | Retained realtime window (64 versions) | configuration |

## Frozen shapes with provisional values

The *shape* of these fields is frozen; their *numbers* depend on open product decisions and may
change without an API change:

* LUNA-01 v0.2.0 gameplay values (battery 240 kWh, array 12 kW: PLAYTEST-FROZEN, D23) and every
  value derived from them.
* Risk index and its drivers (weights provisional, D22).
* Future Lens `confidence` (formula provisional, D6; `provisional: true`).
* Engineering Profile dimension values (weights provisional, D5; `provisional: true`).
* Objective thresholds and outcome rules (D3).
* `label_key` / `message_key` values: stable identifiers for client-side text; the texts
  themselves are not part of the backend.

## Changing the contract

1. The OpenAPI schema is snapshotted in `tests/fixtures/contract/openapi-v1.json`;
   `tests/test_contract_api.py::test_openapi_schema_is_unchanged` fails on **any** difference
   and prints what changed (`REMOVED path`, `changed schema X (removed fields: […])`, …).
2. The contract examples in `tests/fixtures/contract/examples/` are regenerated
   deterministically; `test_v020_contract_is_deterministic` fails when a response changes.
3. To change either: make the change, run `python -m app.tools.openapi_snapshot --check` and
   review every line, classify it (additive or breaking) against the rules above, update this
   document and [API_CONTRACT.md](API_CONTRACT.md), then regenerate
   (`python -m app.tools.openapi_snapshot --write`, `python -m app.tools.contract_fixtures --write`)
   and review the fixture diff. A breaking change to a FROZEN part is not allowed in v1.

## Changes in Phase 4 to pre-existing endpoints

Phase 4 is the first frontend-facing freeze. No frontend existed, so these deliberate changes to
the Phase 1–3 API were made before freezing:

| Change | Before | After |
|---|---|---|
| Error `code` | specific lowercase code, e.g. `stale_sequence` | public code from the frozen list (`STALE_STATE`); the specific code moved to `reason`; new fields `recoverable`, `state_version` |
| Decision that exists but is impossible now | `422` | `409 DECISION_UNAVAILABLE` (`422 INVALID_DECISION` is kept for malformed decisions) |
| WebSocket frames | `state_update`, `event`, … with `{type, session_id, timeline_id, tick, decisions_applied, payload}`; first frame a state snapshot | `odyssey.realtime.v1` envelopes and control frames (`CONNECTED` first); resume support |
| Omniscient Future Lens on the internal endpoint | allowed by the default role policy | requires `ODYSSEY_FUTURE_LENS_OMNISCIENT_ENABLED=true` (off by default) on every Future Lens endpoint |
| `seed` in session views | always present | `null` when internal endpoints are disabled (production) |
| Raw engine endpoints | always served | tag `internal`; 404 in production |
| Future phase names in session / mission catalogue views (`scenario.phases`) | all listed | phases withheld until entered are omitted there (session-independent views); the bootstrap lists them by position with `id: null` |
| `simulation_usage` of science evidence | could name unforeseeable scenario events | such references read `events.unforeseeable` |
| Responses of state-changing endpoints | — | additive `state_version` fields |
