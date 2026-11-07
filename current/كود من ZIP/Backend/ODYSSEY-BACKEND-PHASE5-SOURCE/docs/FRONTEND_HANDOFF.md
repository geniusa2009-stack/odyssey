# Frontend Handoff

For the team that will build the ODYSSEY client. It says what to call, what to trust and what
never to compute yourself. It prescribes no visual design. Field-level reference:
[API_CONTRACT.md](API_CONTRACT.md); what is stable: [API_FREEZE_V1.md](API_FREEZE_V1.md)
(depend only on **FROZEN** parts); real responses: `tests/fixtures/contract/examples/`.

## The rule

**The simulation owns truth. The backend exposes it. The client presents it.** Everything a
player sees — numbers, statuses, which decisions are legal, what an outcome means — comes from
the backend. The client never runs, approximates or extrapolates the simulation.

## Endpoints you need

| Purpose | Call |
|---|---|
| Feature detection | `GET /api/v1/capabilities` (also inside the bootstrap) |
| Start a mission | `POST /api/v1/mission-sessions` (with `Idempotency-Key`) |
| Load / resume a mission | `GET /api/v1/mission-sessions/{id}/bootstrap` |
| Current state (refresh, recovery) | `GET .../snapshot` |
| Legal decisions | `GET .../decision-options` (also `snapshot.decisions`) |
| Make a decision | `POST .../decision-commands` |
| Advance time | `POST .../advance-commands` |
| Objectives, radiation, one resource | `GET .../objectives`, `.../radiation-budget`, `.../resources/{resource_id}` |
| Live updates | WebSocket `/api/v1/ws/mission-sessions/{id}` |
| Missed updates (REST) | `GET .../events?last_event_id=…` |
| Future Lens | `POST .../future-lens/projections` |
| Black Box | `GET .../black-box/summary` |
| Rewind | `GET .../rewind-points`, `GET .../rewind-points/{decision_id}/preview`, `POST .../timeline-branches`, `GET .../timelines` |
| End of mission | `GET .../completion`, then Black Box, `GET .../mission-dna/share`, `GET .../engineering-profile` |
| Decision log | `GET .../history` |
| Science sources | `GET /api/v1/science/claims` |
| ORION (provisional) | `POST .../orion/explain` |

Do not use endpoints tagged `internal` (`/state`, `/timeline`, `/decisions`, `/advance`,
`/rewind`, `/future-lens`, `/black-box`, `/trace`, `/profile`, `/mission-dna`, `/verify`).
They expose raw engine objects, are not frozen, and return 404 in production.

## What to trust, and what not to calculate

Trust and display as given:

* every value, unit and `display_precision` (already rounded; do not add digits);
* `state` (`nominal`/`degraded`/`critical`) and `warning_state` of resources, systems and crew —
  they come from the scenario's own thresholds and alert rules;
* `available` / `unavailable.reason` of decision options, and their `parameters` ranges;
* objective statuses, `completion_fraction`, `margin`, `blockers` and tier `still_possible`;
* the radiation budget, including `projected_dose_msv` (baseline rate only — say so; the
  `projection_statement` field has the wording);
* outcome code and tier; Black Box root causes and verdicts.

Never calculate client-side:

* resource consumption, battery charge, dose accumulation, temperatures, risk, or any future
  value — ask Future Lens;
* whether a decision is allowed — read `decision-options`; it changes with the state;
* status colours from your own thresholds — use `state` / `warning_state`;
* trends — use `trend` (it is `insufficient_data` when the backend has no earlier recorded state;
  show that rather than inventing a direction);
* future phase names — show `snapshot.phase.next_phase` only when it is not `null`; when
  `next_phase_withheld` is true the next chapter is deliberately unannounced (do not fill it in
  from `index`/`total` or old data). In `bootstrap.scenario.phases`, entries with
  `withheld: true` have no name until the mission enters them; refresh the list from a later
  bootstrap or from `PHASE_CHANGED` events ([phase visibility](API_CONTRACT.md#phase-visibility));
* probabilities of success — the backend deliberately computes none; `still_possible` is logic,
  not a chance;
* anything from the seed or hidden events — the contract does not contain them, by design.

Text: fields named `label_key`, `message_key` and `reason` are stable identifiers for your own
copy. Labels such as `label` on metrics are developer English, not final copy.

## Starting and loading a mission

```text
POST /mission-sessions {"participants": [...]}  + Idempotency-Key  → {id}
GET  /mission-sessions/{id}/bootstrap                               → render from snapshot
open WebSocket /ws/mission-sessions/{id}                            → CONNECTED
```

Store the session id. To resume later (new tab, reload), call the bootstrap again; nothing else
is needed. The bootstrap holds the versions, capabilities, the scenario's static description
(phases, objectives, crew, subsystems, resources), the session summary and the full snapshot.

Check `capabilities` before showing a feature (`future_lens`, `rewind`, `radiation_budget`,
`black_box`, …). `radiation_budget` is false for old v0.1.0 sessions.

## Submitting decisions

1. Show options from `snapshot.decisions.options` (or `decision-options`). Disabled options
   carry `unavailable.reason`. `impact` (`major` / `local`) and `category` help you group them;
   `tools` lists Future Lens and ORION, which are not decisions.
2. Send the `option_id`, the `parameters` (only for options that declare them) and the
   `state_version` you are looking at, with a fresh `Idempotency-Key`:

   ```json
   POST .../decision-commands
   {"option_id": "set_crew_location:shelter", "parameters": {}, "expected_state_version": 7}
   ```
3. On `201`, apply `hud` and `state_version` from the response (realtime events will also
   arrive; they carry the same version — apply each version once).
4. On network failure, **retry with the same `Idempotency-Key` and the same body**. If the first
   attempt went through, you get its response again (`Idempotent-Replayed: true`); nothing is
   applied twice.

Advancing time works the same way with `POST .../advance-commands {"ticks", "expected_state_version"}`.

## Handling errors and 409 STALE_STATE

Branch on `error.code` (frozen list); show or log `error.reason` (specific); use
`error.recoverable`.

| Code | What to do |
|---|---|
| `STALE_STATE` (409) | Someone or something changed the state. Fetch `GET .../snapshot`, re-render, and let the player re-confirm. **Do not resend automatically**: the decision may no longer make sense. `error.state_version` is the current version. |
| `DECISION_UNAVAILABLE` (409) | The option exists but is impossible now (`reason`, e.g. `science_busy`). Refresh options. |
| `INVALID_DECISION` (422) | Client bug (unknown option, bad parameters). Do not retry. |
| `MISSION_COMPLETE` (409) | The timeline has ended: go to the completion view. |
| `RATE_LIMITED` (429) | Wait and retry. |
| `SESSION_NOT_FOUND`, `INVALID_TIMELINE` (404) | Session or timeline does not exist (or decision not in it). |
| `PERMISSION_DENIED` (403) | Role or server setting forbids it (e.g. omniscient Future Lens). |
| `SIMULATION_ERROR` (500) | Stored data failed an integrity check. Report it with `request_id`. |

Every response echoes `X-Request-ID`; log it with errors.

## Consuming realtime updates

Each committed change produces an ordered group of events with one `state_version`:
`TIMELINE_CHANGED`? → `DECISION_ACCEPTED`? → mission events (`SYSTEM_ALERT`, `PHASE_CHANGED`,
`OBJECTIVE_UPDATED`, `MISSION_EVENT`) → `RESOURCE_CHANGED` → `MISSION_STATE_CHANGED` →
`MISSION_COMPLETED`?

Client algorithm:

```text
held = snapshot.state_version; timeline = snapshot.timeline.id
on event e:
    if e.seq < 0:                       # FUTURE_LENS_READY / ORION_MESSAGE: informational
        handle and continue
    if e.timeline_id != timeline: ignore (or switch timelines after a TIMELINE_CHANGED you asked for)
    if e.state_version <= held: ignore  # duplicate
    if e.prev_state_version != held: gap → fetch snapshot, set held, continue
    apply e; when e.seq == e.seq_count - 1: held = e.state_version
```

Applying `RESOURCE_CHANGED.hud` updates headline numbers; for full detail after a group
(resources, systems, objectives), fetch the snapshot, or refresh only what the group touched.
Remember the last `event_id` you applied, for resume.

## Reconnecting

Reconnect the WebSocket with `?last_event_id=<last applied>`:

* `RESUMED` → the missed events follow in order; apply them with the algorithm above.
* `RESYNC_REQUIRED` (`events_expired`, `timeline_changed`, …) → fetch the snapshot and continue.
* No cursor → `CONNECTED`; fetch the snapshot.

Send `{"type": "ping"}` periodically if your platform drops idle sockets; the reply is `PONG`.
Without a WebSocket, poll `GET .../events?last_event_id=…` the same way.

## Future Lens

```json
POST .../future-lens/projections
{"candidates": [{"label": "shelter", "decisions": [{"option_id": "set_crew_location:shelter"}]}],
 "horizon_ticks": 24, "samples": 4}
```

* Candidates use the same `option_id`s as decision commands; it never changes the mission.
* Show `knowledge_boundary.statement` with the result: projections use only what is known now
  and never anticipate unforeseeable events.
* Per branch: projected `resources` (`start`, `end`, `end_min`/`end_max` over samples, `worst`),
  `warnings` (with `introduced_by_candidate`), `objectives` (projected statuses), `risk`,
  `confidence` (provisional), `assumptions`, `explanations` (causal chains).
* A candidate that is impossible comes back `valid: false` with `rejection.reason`.
* `prediction_mode: "omniscient"` is a teacher/debug tool, normally disabled
  (`capabilities.future_lens_omniscient`).

## Black Box

`GET .../black-box/summary` after a mission (or at any time on a timeline): the outcome,
`blocked_tiers`, and per failed objective a `shortfall` with triggers, root decisions (only
decisions proven harmful by a counterfactual replay), decisions on the causal path that had no
effect, non-decision causes, intermediate effects, the consequence and a causal chain. Present
root decisions as causes only as the backend lists them; do not infer blame elsewhere.

## Rewind

1. `GET .../rewind-points` → past decisions.
2. `GET .../rewind-points/{decision_id}/preview` → fork tick, how many decisions would be
   discarded, the HUD at the fork. Nothing is created.
3. `POST .../timeline-branches {"decision_id", "alternative": {"option_id", "parameters"}?, "activate": true}`
   with an `Idempotency-Key` → the new timeline. The original timeline never changes.
4. With `activate: true` the session's active timeline switches: call the bootstrap (or the
   snapshot) again; the WebSocket sends `TIMELINE_CHANGED`, and a resume on the old timeline
   answers `RESYNC_REQUIRED (timeline_changed)`.
5. `GET .../timelines` → the tree for a timeline picker; read any timeline with
   `?timeline_id=` on the read endpoints.

## Mission completion

The mission ends at the last tick or on crew loss. You will see `status: "concluded"`, an
`outcome` in the snapshot, and a realtime `MISSION_COMPLETED` event. Then:

* `GET .../completion` — outcome code and tier, objective results, which better tiers were
  blocked and by which objectives, duration, decisions, final HUD, links to the analyses;
* `GET .../black-box/summary`, `GET .../mission-dna/share`, `GET .../engineering-profile`.

Tiers: `exceptional`, `success`, `partial`, `mission_failed` (the crew may be safe),
`critical_failure` (crew loss). Mission DNA is share-safe (no ids, no seed); the Engineering
Profile is provisional (weights are an open product decision, D5) and has no archetype.

Commands on a concluded timeline answer `409 MISSION_COMPLETE`; rewinding still works.

## Versions

* **API version** (`v1`, in the URL): changes only additively; breaking changes would be `v2`.
* **Scenario version** (`scenario.scenario_version`, e.g. `0.2.0`): the mission content pinned to
  each session at creation. A session never moves to a newer scenario; old sessions keep their
  numbers and replay identically. Different sessions can have different scenario versions —
  render from the bootstrap's scenario description, not from constants in your code.
* **Read-model version** and **realtime contract** (`odyssey.realtime.v1`) are reported in the
  bootstrap; check them if you cache shapes.
* Never infer features from version strings; use `capabilities`.

## Development setup

The API runs with zero infrastructure (SQLite, in-memory realtime) — see
[LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). The contract examples in
`tests/fixtures/contract/examples/` are deterministic and suitable as mock data. OpenAPI is at
`/openapi.json` (and `/docs` outside production); a normalized copy is
`tests/fixtures/contract/openapi-v1.json`.
