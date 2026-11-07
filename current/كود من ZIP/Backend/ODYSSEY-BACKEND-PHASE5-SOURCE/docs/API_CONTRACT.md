# API Contract (v1)

The frontend-safe application contract of the ODYSSEY backend. Which parts are frozen is listed
in [API_FREEZE_V1.md](API_FREEZE_V1.md); how a client should use them is in
[FRONTEND_HANDOFF.md](FRONTEND_HANDOFF.md). The response examples for bootstrap, resources,
decision options, decision results, realtime events, radiation, Future Lens and Black Box are
trimmed from the deterministic contract fixtures in `tests/fixtures/contract/examples/`
(regenerate with `python -m app.tools.contract_fixtures --write`; full responses are there).
Timestamps (normalised in the fixtures) and the short request sketches are illustrative.

## Principles

* **The simulation owns truth.** Every response is a *projection* (`app/read_models/`) computed
  from the engine's metric registry, the head state of a timeline and the scenario definition.
  No read model re-implements a simulation formula; status bands come from the scenario's own
  severity scales and alert rules.
* **No hidden information.** No response of the contract contains the random seed, raw engine
  state, active-modifier end ticks, event trigger or effect parameters, unopened science windows,
  or anything about unforeseeable future events. This is tested by comparing every projection
  against a variant scenario without future hidden events (`tests/test_contract_hidden_information.py`).
* **Honest precision.** Numbers are rounded to a per-unit display precision before they leave the
  backend (e.g. `fraction` 3 decimals, `ppm` 0, `mSv` 2); resources carry `display_precision`.
  Trends come only from recorded states; with no earlier recorded state the trend is
  `insufficient_data` instead of a guess.
* **Closed shapes.** Every read model forbids unknown fields. New fields may be *added* (clients
  must ignore fields they do not know); nothing is removed or renamed within v1.

## Versions

Four independent version numbers; a client never infers features from them (use capabilities).

| Field | Where | Meaning |
|---|---|---|
| `api.api_version` | bootstrap, `/capabilities` | URL major version (`v1`) |
| `api.server_version` | bootstrap, `/capabilities`, `/health` | backend build |
| `api.read_model_version` | bootstrap, `snapshot.read_model_version` | read-model generation (1) |
| `api.realtime_contract` | bootstrap, every realtime frame (`contract`) | `odyssey.realtime.v1` |
| `scenario.scenario_version` | bootstrap | the scenario **pinned to this session** (e.g. `0.2.0`, or `0.1.0` for old sessions) |

## Starting or loading a mission

```http
POST /api/v1/mission-sessions          {"seed": 42, "participants": [{"handle": "cdr", "role": "commander"}]}
→ 201 {"id": "…", "scenario": {...}, "timelines": [...], "seed": 42, ...}
GET  /api/v1/mission-sessions/{id}/bootstrap
```

`seed` is optional (random when omitted) and is `null` in responses when internal endpoints
are disabled (production): with the seed, a client could compute hidden future events offline.

### Bootstrap

One request initialises a client:

```json
{
 "api": {"api_version": "v1", "server_version": "0.1.0", "read_model_version": 1,
         "realtime_contract": "odyssey.realtime.v1", "error_codes": ["AI_UNAVAILABLE", "..."]},
 "capabilities": {"future_lens": true, "future_lens_omniscient": false, "black_box": true,
                  "rewind": true, "orion": true, "orion_ai_provider": false,
                  "multiplayer_ready": false, "science_evidence": true, "radiation_budget": true,
                  "mission_dna": true, "engineering_profile": true, "idempotency": true,
                  "optimistic_concurrency": true, "realtime_resume": true,
                  "nasa_live_data": false, "internal_endpoints": true},
 "scenario": {"mission_id": "luna-01", "scenario_version": "0.2.0", "tick_hours": 1.0,
              "max_ticks": 240, "phases": [...], "objectives": [...], "outcomes": [...],
              "crew": [...], "subsystems": [...], "components": [...], "resources": [...],
              "dose_limit_msv": 15.0},
 "session": {"session_id": "…", "status": "active", "active_timeline_id": "…",
             "participants": [...], "timelines": [...], "future_lens_requests": 0},
 "snapshot": { "…": "see Snapshot" },
 "realtime": {"path": "/api/v1/ws/mission-sessions/{id}", "contract": "odyssey.realtime.v1",
              "resume_query": ["last_event_id", "timeline_id", "last_state_version", "last_seq"],
              "events_path": "/api/v1/mission-sessions/{id}/events"},
 "endpoints": {"snapshot": "/api/v1/mission-sessions/{id}/snapshot", "...": "..."}
}
```

No history is included. Size of a new LUNA-01 session's bootstrap: ≈ 48 KB measured as
`len(json.dumps(body))` (Python's default separators), ≈ 44 KB as compact JSON
(`separators=(",", ":")`). The original Phase 4 measurement (≈ 51 KB) used the default
separators; see [RECOVERY_PROVENANCE.md](RECOVERY_PROVENANCE.md) for the difference. Future phases
that are withheld appear in `scenario.phases` as `{"id": null, "withheld": true}`
([Phase visibility](#phase-visibility)). `capabilities.radiation_budget` is per scenario
(false for v0.1.0 sessions, which have no mission dose limit).

## Snapshot

`GET /mission-sessions/{id}/snapshot[?timeline_id=]` — the authoritative current state of one
timeline. Use it after a refresh, a reconnect, a `RESYNC_REQUIRED` frame or a `409`.

| Field | Content |
|---|---|
| `state_version`, `state_hash`, `status`, `timeline` | version of this state, its hash, `active`/`concluded`, timeline reference |
| `clock` | `tick`, `max_ticks`, `tick_hours`, `elapsed_hours`, `remaining_hours` |
| `phase` | `id`, `kind`, `index`/`total`, `entered_tick`, `next_phase` (`null` when withheld, see [Phase visibility](#phase-visibility)), `next_phase_withheld`, phase history |
| `hud` | compact headline numbers (also the payload of `RESOURCE_CHANGED`) |
| `resources[]` | power, battery, oxygen, co2, water, food, thermal, communications, science, radiation, rover |
| `systems` | power, habitat, life_support, thermal, communications, science, rover: mode, load, supply, component health and condition |
| `crew` | per member: role, status, health and band, fatigue, dose, location, shelter/EVA |
| `objectives` | the objective outlook (below) |
| `alerts[]` | active alerts: `id`, severity, metric, value, threshold, `message_key` |
| `radiation` | the radiation budget (below) |
| `science` | points, campaigns completed, data, active campaign, **opened** windows only |
| `risk` | risk index, band, top drivers (provisional weights, D22) |
| `decisions` | available decisions and informational tools (below) |
| `outcome` | `null` until the mission ends; then code, tier, objectives |

A resource:

```json
{"id": "battery", "label": "Battery", "metric": "power.battery_soc", "value": 0.9,
 "unit": "fraction", "display_precision": 3, "state": "nominal", "pressure": 0.0,
 "warning_state": "none", "fill_fraction": 0.9, "range": {"min": 0.0, "max": 1.0},
 "thresholds": {"direction": "below", "nominal": 0.4, "critical": 0.05},
 "trend": {"basis": "insufficient_data", "direction": "unknown", "delta": null},
 "details": [{"id": "charge_kwh", "label": "Battery charge", "value": 216.0, "unit": "kWh"}]}
```

`state` is `nominal`/`degraded`/`critical` from the scenario severity scale; `warning_state` is
the worst active alert on the resource's metrics. `GET .../resources/{resource_id}` adds the
alert rules and the recorded history (persisted snapshots only).

### Objective outlook

`GET .../objectives` (also `snapshot.objectives`). Per objective: `id`, `category` (pillar),
`required`, `status` (`pending`/`achieved`/`failed`), `kind`, `evaluated`
(`continuously`/`at_mission_end`), the **rule as data** with targets and current values,
`completion_fraction` for single "reach at least X" targets, `margin` for single "stay within X"
constraints, and `blockers` observable now (`objective_failed`, `input_critical`).

`tiers[]` says for each better outcome tier whether it is `still_possible` — logic over the
outcome rules and the objective statuses, **not a probability**. No probability is ever
computed.

### Radiation budget

`GET .../radiation-budget` (also `snapshot.radiation`); during the tick-122 solar particle event, crew still in the habitat:

```json
{"dose_limit_msv": 15.0, "max_dose_msv": 5.95, "dose_margin_msv": 9.05,
 "projected_dose_msv": 9.95, "projected_dose_margin_msv": 5.05,
 "projection_basis": "baseline_rate_current_locations",
 "projection_statement": "Projected dose assumes the background dose rate for the rest of the mission at the crew's current locations. It does not anticipate space-weather events.",
 "surface_dose_rate_msv_h": 2.28, "background_dose_rate_msv_h": 0.057,
 "received_dose_rate_msv_h": 1.368, "acute_threshold_msv_h": 0.5,
 "exposure_status": "elevated", "budget_state": "within_budget", "warning_state": "warning",
 "crew_in_shelter": 0, "crew_on_eva": [],
 "crew": [{"crew_id": "crew_cdr", "dose_msv": 5.95, "location": "habitat", "margin_msv": 9.05}]}
```

The projection uses the background rate only; it is identical with or without a future storm
(tested).

## Phase visibility

Phases are the scenario's designed mission chapters on a schedule. A chapter's *name* can tell
what is coming (a chapter built around a solar storm), so the names of **future** phases follow
one general rule (`app/read_models/visibility.py`), computed from the scenario's phase schedule
and event foreseeability — never from names:

A future simulated phase is **announced** (its name may be shown before it begins) only if
(1) its start is on the clock (`time.tick >= N` transitions from the first phase),
(2) a planned milestone — a *foreseeable* scheduled event — lies in its window, and
(3) no unforeseeable event can only fire inside its window. Every other future phase is
**withheld until entered**.

* `snapshot.phase.id` (the current phase), `phase.history` and every phase already entered are
  always visible; `conclusion`/`analysis` phases are always visible.
* `snapshot.phase.next_phase` is `null` with `next_phase_withheld: true` when the next phase is
  withheld (it is `null` with `next_phase_withheld: false` when there is no next phase).
* `bootstrap.scenario.phases` keeps every phase in order; withheld ones are
  `{"id": null, "kind": "simulated", "withheld": true}` until entered, so `index`/`total` stay
  consistent.
* Future Lens `branches[].projected_phase` is `null` with `projected_phase_withheld: true` in
  `known_only` mode when the projected phase is withheld (omniscient mode shows it by design).
* `PHASE_CHANGED` realtime events name the phase being entered, i.e. the new current phase.

Withholding never depends on whether a hidden event exists (condition 2 is positive; a chapter
without a planned milestone is withheld even when nothing unforeseeable happens in it), so a
`null` reveals nothing. LUNA-01 v0.2.0: `power_management`, `environmental_emergency`,
`communication_loss` and `resource_cascade` are withheld until entered. Tested in
`tests/test_phase_visibility.py`, including a scan of every frontend-safe response and realtime
frame for names that are not known yet.

The same principle applies to events: identifiers of unforeseeable scenario events never appear
in static content — a science claim's `simulation_usage` shows `events.unforeseeable` instead.

## Decisions

### Options

`GET .../decision-options` (also `snapshot.decisions`). The backend decides what is legal:

```json
{"option_id": "set_thermal_setpoint", "decision_type": "set_thermal_setpoint",
 "category": "thermal", "impact": "local", "available": true, "unavailable": null,
 "is_current_setting": false, "affected_systems": ["thermal", "power"],
 "parameters": [{"name": "target_c", "type": "number", "min": 10.0, "max": 26.0, "unit": "°C", "current": 21.0}],
 "label_key": "decision.set_thermal_setpoint", "required_capability": null}
```

```json
{"option_id": "stop_science_activity", "available": false, "impact": "major",
 "unavailable": {"reason": "no_active_science", "message": "no science activity is running"}, "...": "..."}
```

* `option_id` grammar: `<decision_type>[:<arg>[:<arg>]]`, e.g. `set_subsystem_mode:comms:eco`,
  `start_science_activity:regolith_survey`, `rover_command:traverse:far_crater`.
* `available` / `unavailable.reason` come from the engine's own validation (on a private copy of
  the state). Science options appear only once their window has opened.
* `impact`: `major` (HIGH or MEDIUM in the Phase 3 measurement, [DECISION_IMPACT_MODEL.md](DECISION_IMPACT_MODEL.md))
  or `local` (LOCAL/REDUNDANT; maintenance is LOCAL / CUMULATIVE by decision D24).
* `tools[]`: informational options (`tool:future_lens`, `tool:orion`, `impact: "informational"`).
  They never change state and are not submitted as decision commands.

### Decision command

```http
POST /mission-sessions/{id}/decision-commands
Idempotency-Key: 7b1c9e0f-retry-1          (optional)
{"option_id": "start_science_activity:regolith_survey", "parameters": {},
 "expected_state_version": 2, "timeline_id": null, "participant_id": null, "metadata": {}}
```

```json
201 {"accepted": true, "session_id": "…", "timeline_id": "…",
     "state_version": 3, "prev_state_version": 2, "tick": 15,
     "decision": {"decision_id": "dec_hlv7xyiiwzpubrgsagyj", "sequence": 1, "tick": 15,
                  "decision_type": "start_science_activity",
                  "option_id": "start_science_activity:regolith_survey", "parameters": {},
                  "affected_systems": ["science", "power"], "inherited": false,
                  "participant_id": null},
     "hud": {"tick": 15, "battery_soc": 1.0, "oxygen_days": 7.44, "...": "..."},
     "events": [{"kind": "decision_applied", "key": "start_science_activity", "...": "..."}],
     "events_truncated": false}
```

`expected_state_version` is **required**. Parameterised options take `parameters`
(`set_thermal_setpoint: {"target_c"}`, `set_ration_level: {"level"}`); others take none.

### Advance command

```http
POST /mission-sessions/{id}/advance-commands   {"ticks": 24, "expected_state_version": 3}
→ 200 {"state_version": 4, "prev_state_version": 3, "from_tick": 15, "to_tick": 39,
       "ticks_run": 24, "concluded": false, "phase": "…", "outcome": null, "hud": {...},
       "events": [...], "events_truncated": false}
```

The engine stops early when the mission concludes (`ticks_run` < `ticks`).

## State versioning and optimistic concurrency

* Every timeline has a **state version**: an integer that increases by exactly 1 with every
  committed change (decision, advance; a new timeline starts at 1). Read models carry it.
* Commands carry `expected_state_version`. If the timeline moved on, the command is **not
  applied** and the answer is:

```json
409 {"error": {"code": "STALE_STATE", "reason": "stale_state", "recoverable": true,
               "message": "the timeline has changed since the state you based this request on",
               "state_version": 4,
               "details": {"timeline_id": "…", "head_tick": 3, "head_sequence": 0,
                           "expected_state_version": 1},
               "request_id": "…"}}
```

* Concurrent commands on one version: exactly one wins; the others get `STALE_STATE` (tested on
  SQLite and PostgreSQL with row locks).

## Idempotency

`Idempotency-Key` (8–128 characters of `[A-Za-z0-9_.:-]`) on `POST /mission-sessions`,
`/decision-commands`, `/advance-commands` and `/timeline-branches` (and the internal command
endpoints). The successful response is stored in the same transaction as the change.

* Same key, same request → the stored response, unchanged, with header `Idempotent-Replayed: true`.
  Nothing is applied twice, also when the retry races the original request.
* Same key, different request → `422 IDEMPOTENCY_KEY_REUSED`.
* Failed requests are not stored: a retry is executed again.
* Keys are scoped per principal (authentication seam; `anonymous` today), endpoint and session.

## Errors

One envelope everywhere, never a stack trace:

```json
{"error": {"code": "DECISION_UNAVAILABLE", "reason": "no_active_science",
           "message": "no science activity is running", "details": {},
           "request_id": "3f2a…", "recoverable": true, "state_version": 2}}
```

`code` is from a deliberately small, frozen list and fixes the HTTP status; `reason` is the
specific machine-readable cause (more reasons may be added; treat an unknown reason as its
`code`); `recoverable` is true when retrying after a refresh or a wait can succeed.

| `code` | HTTP | Recoverable | Example reasons |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | no | `validation_error` (schema; `details.errors` lists fields) |
| `INVALID_REQUEST` | 422 | no | `too_many_ticks`, `bad_idempotency_key`, `cursor_required`, `bad_event_id`, `unknown_participant`, `metric_required` |
| `INVALID_DECISION` | 422 | no | `unknown_option`, `option_type_mismatch`, `bad_parameters`, `unknown_subsystem`, `mode_not_supported`, `setpoint_out_of_range`, `ration_out_of_range`, `unknown_component` |
| `DECISION_UNAVAILABLE` | 409 | yes | `no_active_science`, `science_busy`, `opportunity_unavailable`, `requires_rover`, `maintenance_in_progress`, `no_crew_available`, `crew_unavailable`, `eva_in_progress`, `rover_*`, `no_link` |
| `STALE_STATE` | 409 | yes | `stale_state`, `stale_sequence`, `concurrent_modification`, `write_conflict` |
| `MISSION_COMPLETE` | 409 | no | `mission_concluded` |
| `IDEMPOTENCY_KEY_REUSED` | 422 | no | `idempotency_key_reused` |
| `SESSION_NOT_FOUND` | 404 | no | `session_not_found` |
| `INVALID_TIMELINE` | 404 | no | `timeline_not_found`, `decision_not_in_timeline` |
| `NOT_FOUND` | 404 | no | `not_found`, `resource_not_found`, `evidence_not_found`, `mission_not_found` |
| `METHOD_NOT_ALLOWED` | 405 | no | `method_not_allowed` |
| `PERMISSION_DENIED` | 403 | no | `role_forbidden`, `omniscient_disabled` |
| `PAYLOAD_TOO_LARGE` | 413 | no | `payload_too_large` (body > 64 KiB) |
| `RATE_LIMITED` | 429 | yes | `rate_limited` |
| `SIMULATION_ERROR` | 500 | no | `replay_divergence`, `state_hash_mismatch` (stored data failed an integrity check) |
| `AI_UNAVAILABLE` | 503 | yes | reserved (ORION currently degrades to its grounded mock) |
| `NASA_PROVIDER_UNAVAILABLE` | 503 | yes | reserved (NASA data currently falls back to fixtures) |
| `INTERNAL_ERROR` | 500 | no | `internal_error` |

## Realtime

`GET /api/v1/ws/mission-sessions/{session_id}` (WebSocket). Server → client only; commands go
through REST. Every frame is JSON with `"contract": "odyssey.realtime.v1"`.

### Events

```json
{"contract": "odyssey.realtime.v1", "event_id": "{timeline_id}:3:0", "type": "DECISION_ACCEPTED",
 "session_id": "…", "timeline_id": "…", "state_version": 3, "prev_state_version": 2,
 "seq": 0, "seq_count": 3, "sim_tick": 15, "sim_time_hours": 15.0,
 "server_time": "2026-10-19T06:00:00+00:00",
 "payload": {"decision": {"option_id": "start_science_activity:regolith_survey", "...": "..."}}}
```

| Type | Payload |
|---|---|
| `TIMELINE_CHANGED` | `timeline_id`, `parent_timeline_id`, `replaced_decision_id`, `fork_tick`, `active`, `state_version` |
| `DECISION_ACCEPTED` | `decision` (as in the decision command response) |
| `SYSTEM_ALERT` | `action` (`raised`/`cleared`/`warning`/`cascade`), `event` |
| `PHASE_CHANGED` | `from`, `to`, `event` |
| `OBJECTIVE_UPDATED` | `objective`, `status`, `category`, `event` |
| `MISSION_EVENT` | `event` (milestones, science windows, space weather, faults, comms) |
| `RESOURCE_CHANGED` | `hud` |
| `MISSION_STATE_CHANGED` | `cause` (`session_created`/`decision`/`advance`/`timeline_created`), `from_tick`, `tick`, `phase`, `status`, `state_hash`, `engine_events`, `events_truncated` |
| `MISSION_COMPLETED` | `outcome` |
| `FUTURE_LENS_READY` | `request_hash`, `branches`, `prediction_mode` (auxiliary) |
| `ORION_MESSAGE` | ORION response (auxiliary) |

`event` payloads are frontend-safe mission events: id, tick, kind, key, severity,
`message_key` and cleaned `data` (scenario trigger/effect parameters removed).

### Ordering rules

1. One committed transition → one group of events with the same `state_version`, `seq` =
   0…`seq_count`−1, `prev_state_version` = the version it was applied to.
2. Inside a group (deterministic): `TIMELINE_CHANGED`? · `DECISION_ACCEPTED`? · engine events in
   emission order (at most 200; `events_truncated` says if more happened) · `RESOURCE_CHANGED` ·
   `MISSION_STATE_CHANGED` · `MISSION_COMPLETED`?
3. Groups of one timeline are published in version order, only after the transaction commits.
4. `event_id` = `{timeline_id}:{state_version}:{seq}`: deterministic and unique. A client applies
   a group when `prev_state_version` equals the version it holds; otherwise it has a gap.
5. Auxiliary events (`FUTURE_LENS_READY`, `ORION_MESSAGE`) change nothing: `seq: -1`,
   `seq_count: 0`, a random id `{timeline_id}:{version}:aux:{hex}`, not retained.

### Control frames

`CONNECTED` (fresh connection: `timeline_id`, `state_version`, `sim_tick`, `snapshot_path`),
`RESUMED` (`replayed` = number of retained events that follow), `RESYNC_REQUIRED` (`reason`,
`snapshot_path`), `PONG` (reply to a client `{"type": "ping"}`). Control frames have no
`event_id`. Other client frames, frames over 1 KiB and malformed frames are ignored. The socket
closes with `1008` for a malformed or unknown session, a malformed resume cursor or a
disallowed `Origin`.

## Reconnect and resume

Reconnect with `?last_event_id=…` (or `?last_state_version=N[&timeline_id=…][&last_seq=S]`).
The server subscribes before reading, then either:

* sends `RESUMED` followed by every retained event after the cursor, in order, and continues
  live (events from the backlog are not repeated), or
* sends `RESYNC_REQUIRED` with a reason — fetch `GET .../snapshot` and continue live.

The REST equivalent is `GET .../events?last_event_id=…` → `{"resync_required": false, "events": [...]}`
or `{"resync_required": true, "reason": "events_expired"}`.

| Reason | Meaning |
|---|---|
| `events_expired` | the cursor is older than the retained window (64 state versions per timeline by default) |
| `timeline_changed` | the session's active timeline is another one (rewind) |
| `unknown_timeline` | the cursor's timeline is not part of this session |
| `unknown_position` | the cursor is ahead of the server |
| `too_many_events` | more than 1,000 events to replay |
| `events_unavailable` | the retained log has a hole at the cursor |

## Future Lens

```http
POST /mission-sessions/{id}/future-lens/projections
{"candidates": [{"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}],
 "include_baseline": true, "horizon_ticks": 24, "samples": 4, "prediction_mode": "known_only"}
```

```json
{"base_tick": 123, "state_version": 6, "request_hash": "…",
 "knowledge_boundary": {"prediction_mode": "known_only", "anticipates_unforeseeable_events": false,
   "uses_mission_random_sequence": false,
   "statement": "Projections use only what is known now: the current state, the mission plan, and random faults sampled with seeds derived for the projection (never the mission's own random sequence). Unforeseeable events are never anticipated, whether or not any remain."},
 "horizon": {"requested_ticks": 24, "projected_ticks": 24, "hours": 24.0, "clipped_to_mission_end": false},
 "branches": [{"label": "baseline", "is_baseline": true, "valid": true,
   "resources": [{"metric": "power.battery_soc", "label": "Battery state of charge", "unit": "fraction", "start": 0.97, "end": 0.974, "end_min": 0.974, "end_max": 0.974, "delta": 0.005, "worst": 0.97, "worst_tick": 123, "vs_baseline": null}],
   "warnings": [{"alert_id": "dose_budget_low", "severity": "warning", "metric": "crew.projected_dose_margin_msv", "first_tick": 125, "hours_from_now": 2.0, "sample_fraction": 1.0, "introduced_by_candidate": false}],
   "objectives": [{"objective": "crew_survival", "category": "primary", "status_now": "pending", "projected_status": "pending", "achieved_fraction": 0.0, "failed_fraction": 0.0}],
   "risk": {"end_index": 0.612, "peak_index": 0.616, "peak_tick": 130, "critical_warning_fraction": 1.0},
   "confidence": {"level": "medium", "score": 0.51, "samples": 4, "provisional": true, "horizon_factor": 0.75, "spread_factor": 1.0, "model_factor": 0.8, "knowledge_factor": 0.85},
   "assumptions": ["…", "Unforeseeable events (for example space weather, communication outages and equipment faults) are not anticipated."],
   "explanations": [{"target_metric": "crew.projected_dose_msv", "steps": ["…"], "counterfactual": null}]},
  {"label": "shelter", "is_baseline": false, "decisions": [{"option_id": "set_crew_location:shelter", "parameters": {}}], "...": "..."}]}
```

* Never changes mission state or the state version; publishes `FUTURE_LENS_READY`.
* `projected_phase` follows the [phase visibility](#phase-visibility) rule in `known_only` mode
  (`null`, `projected_phase_withheld: true` when the projected phase is withheld).
* `known_only` (default) never reveals hidden information: unforeseeable events are excluded;
  the assumption naming which events were excluded is replaced by a generic sentence; the
  confidence knowledge factor is constant (whether unforeseeable events remain is itself
  hidden). Tested against a scenario without future hidden events.
* `omniscient` reveals the future (teacher/debug) and is refused (`403 PERMISSION_DENIED`,
  `omniscient_disabled`) unless `ODYSSEY_FUTURE_LENS_OMNISCIENT_ENABLED=true` — on every
  Future Lens endpoint; the role policy (D6) applies on top.
* Limits: 1–4 candidates, ≤ 8 decisions each, horizon 1–240 ticks, 1–16 samples.

## Black Box

`GET .../black-box/summary[?counterfactuals=true]`:

```json
{"mission_status": "concluded", "final_tick": 240,
 "outcome": {"code": "mission_complete_partial", "tier": "partial", "...": "..."},
 "blocked_tiers": {"success": ["life_support_stability", "power_continuity"],
                   "exceptional": ["life_support_stability", "power_continuity", "reserves_at_end", "science_quality"]},
 "shortfalls": [{"objective": "power_continuity", "category": "stability", "kind": "traced",
   "resolved_tick": 224, "blocks_tiers": ["exceptional", "success"],
   "triggers": [{"metric": "power.unmet_kw", "label": "Unmet demand (load shed)", "unit": "kW", "op": ">", "threshold": 0.05, "value": 2.23, "tick": 225}],
   "root_decisions": [{"decision_id": "dec_jzy5ztbgtpofvweqqw4w", "decision_type": "start_science_activity", "option_id": "start_science_activity:ice_core_sampling", "tick": 100, "verdict": "decision_worsened_target"}],
   "decisions_on_path_without_effect": [],
   "other_causes": [{"id": "environment:solar_availability", "kind": "environment", "label": "Natural environment profile (Solar availability)"}],
   "intermediate_effects": [{"metric": "control.discretionary_load_kw", "label": "Demand from discretionary loads (science payload, rover charging)", "unit": "kW"},
                            {"metric": "power.battery_soc", "label": "Battery state of charge", "unit": "fraction"}, "…"],
   "facts": [], "consequence": "blocked outcome tier 'success'",
   "causal_chain": {"target_metric": "power.unmet_kw", "target_tick": 225,
     "steps": [{"kind": "decision", "label": "Decision: start_science_activity", "tick": 100, "via": "set the value of this quantity"},
               {"kind": "metric", "label": "Demand from discretionary loads (science payload, rover charging)", "tick": 101, "value": 1.2, "via": "Science operations and rover charging draw down the battery"}, "…"],
     "counterfactual": {"target_metric": "power.unmet_kw", "target_tick": 225, "verdict": "decision_worsened_target", "with_decision": 2.23, "without_decision": 0.0}}}],
 "key_moments": [{"tick": 139, "category": "phase", "kind": "phase_change", "key": "communication_loss", "severity": null, "data": {"from": "environmental_emergency", "to": "communication_loss"}}],
 "decisions_count": 4, "counterfactuals_evaluated": true,
 "statement": "Decisions are named as root causes only when a counterfactual replay without them makes the failing quantity better. …"}
```

A decision appears in `root_decisions` only with a counterfactual "made it worse" verdict;
decisions on a causal path whose removal changes nothing are listed separately and never
blamed. Dependency-graph internals (node and edge lists) are not exposed.

## Rewind

| Request | Result |
|---|---|
| `GET .../rewind-points` | decisions of the timeline (incl. inherited): `decision_id`, tick, `option_id`, `decisions_discarded_if_replaced` |
| `GET .../rewind-points/{decision_id}/preview` | `fork_tick`, `inherited_decisions`, `discarded_decisions`, `replaced_decision`, `state_at_fork` (HUD) — creates nothing |
| `POST .../timeline-branches` `{"decision_id", "alternative": {"option_id", "parameters"}?, "continue_ticks": 0, "activate": true, "label"?}` | `201` `{timeline, parent_timeline_id, replaced_decision_id, alternative_decision, state_version, active, hud}` |
| `GET .../timelines` | the tree: per timeline `parent_timeline_id`, `children`, fork point, replaced decision, alternative option, status, `is_active`, head, outcome code and tier |

The new timeline starts from the state just before the replaced decision; the source timeline
is never modified (tested: its snapshot and history are unchanged). With `activate: true` the
session's active timeline switches and realtime clients on the old timeline receive
`RESYNC_REQUIRED (timeline_changed)` on reconnect.

## Mission completion

`GET .../completion`: `concluded`, `outcome` (code, tier, achieved and failed objectives),
`objectives` (final statuses), `better_tiers_blocked` (for each better tier, the objectives
that blocked it), `duration`, `decisions_count`, `final_hud`, and `analysis_paths` (Black Box,
Mission DNA, Engineering Profile, history). Before the end `concluded` is false and `outcome`
null. The realtime `MISSION_COMPLETED` event carries the same outcome.

| Outcome code | Tier |
|---|---|
| `mission_complete_exceptional` | `exceptional` |
| `mission_complete` | `success` |
| `mission_complete_partial` | `partial` |
| `mission_failed` | `mission_failed` (the crew may be safe) |
| `mission_failed_crew_loss` | `critical_failure` |

## Engineering Profile, Mission DNA, science claims

* `GET .../engineering-profile` → `dimensions[]` (`id`, `value` 0–1, `contributions`),
  `weights_version`, `provisional: true`, `archetype: null` (not supported until D5),
  `explanation_inputs` (behaviour features), `coverage` (decisions and ticks analysed, whether
  the mission ended, Future Lens requests), `notes`. Weights are unchanged (D5 open).
* `GET .../mission-dna/share` → `code`, `dna_version`, `scenario_id`, `scenario_version`,
  `outcome_code`, `outcome_tier`, `concluded`, `genes`, `comparison_fields`, `share_safe: true`.
  No session, timeline or participant ids and no seed; the same play gives the same code on
  any session.
* `GET /science/claims[/{id}]` → `concept`, `claim`, `value`, `unit`, `source` (`name`,
  `citation`, `url`, `retrieved_date`), `provenance` (`primary_source`/`secondary_source`/
  `unverified`), `verification_status`, `verified` (true only for verified sources),
  `status_label` ("Unverified — educational abstraction, not established science" for
  unverified items), `simulation_usage` (references to unforeseeable events appear as `events.unforeseeable`),
  `simplification`, `confidence`, `notes`.

## Limits

| Limit | Value |
|---|---|
| Request body | 64 KiB (`413`) |
| `advance-commands.ticks` | 1–240 (server maximum `ODYSSEY_MAX_ADVANCE_TICKS`) |
| Decision parameters / metadata | ≤ 4 parameters; ≤ 16 metadata keys of ≤ 64 characters |
| Future Lens | 1–4 candidates, ≤ 8 decisions each, horizon ≤ 240, samples ≤ 16 |
| ORION question | ≤ 500 characters |
| WebSocket client frame | ≤ 1 KiB (larger frames are ignored) |
| Events page | ≤ 1,000 events, otherwise `resync_required` |
| History | `limit` ≤ 2,000 events |
| Retained realtime versions | 64 per timeline (`ODYSSEY_REALTIME_RETAINED_VERSIONS`) |
| Rate limits (per client IP, per minute) | 120 ordinary; 20 expensive: advance commands, history, Future Lens, Black Box, rewind preview, timeline branches, Engineering Profile, Mission DNA, ORION |
