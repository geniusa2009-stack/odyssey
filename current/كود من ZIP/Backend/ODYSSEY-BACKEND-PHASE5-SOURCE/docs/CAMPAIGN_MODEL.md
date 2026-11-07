# Campaign Model

Content: `app/game/content/data/campaign.yaml` (+ `manifest.yaml`). Logic:
`app/game/campaign/campaign.py` (pure).

## Eight phases

| Order | Phase | Authored | Missions | Prerequisites |
|---|---|---|---|---|
| 1 | `EARTH_COMMAND` | yes | `earth_command.station_readiness` | — |
| 2 | `LUNA_01` | yes | `luna_01.the_last_light` (LUNA-01 v0.2.0 simulation, replayable) | Earth Command completed |
| 3 | `LUNAR_SURVIVAL` | no | — | LUNA-01 completed + `power.load_management` ≥ LUNAR_DEMONSTRATED |
| 4 | `LUNAR_EXPLORATION` | no | — | Lunar Survival + `mobility.surface_rover` ≥ LUNAR_DEMONSTRATED |
| 5 | `LUNAR_NETWORK` | no | — | Lunar Exploration + relay and construction ≥ LUNAR_DEMONSTRATED |
| 6 | `DEEP_SPACE_READINESS` | no | — | Lunar Network |
| 7 | `PATH_TO_MARS` | no | — | Deep Space Readiness |
| 8 | `MARS_01` | no | — | Path to Mars + readiness profile `mars_01_human_mission` |

Only content we understand is authored. Later phases define position, prerequisites and gates;
they can become `available` structurally but cannot start until their content exists
(`phase_content_not_authored`).

## States

* Phase: `locked`, `available`, `active`, `completed`, `failed`.
* Mission: `locked`, `available`, `active`, `completed`, `failed`; `attempts`, `best_tier`;
  `replayable` missions can be started again after completion; a failed mission can always be
  retried. Missions are `primary` or `optional` (a phase completes when its primary missions
  are completed).
* Prerequisites (phases and missions): phases completed, missions completed, capabilities at a
  stage, discoveries, certifications, readiness profile. `refresh()` recomputes
  `locked`/`available` after every completion; nothing else can unlock a phase.

## Rules

* **No skipping.** Phases follow content order; a phase is available only when its
  prerequisites hold. `POST /phases/{id}/start` checks prerequisites first
  (`phase_locked` with the exact missing items), and a readiness-gated phase answers
  `mars_mission_locked` (see below). Fuzzing asserts that no later phase is ever active or
  completed while an earlier one is not completed.
* **One active mission.** Starting another is `mission_already_active`.
* **Completion is atomic** (`complete_mission`): completion evidence rules are evaluated, the
  timeline's pending evidence and discoveries are committed to the campaign once, capability
  stages are re-derived, certifications granted, carry rules applied (Earth Command's LUNA-01
  cargo hold lands in the ASTERIA lander hold), persistent infrastructure recorded, the phase
  completed, the next phase refreshed, a history record appended, a `mission_transition`
  checkpoint written and — if the next mission is available — its timeline created in the same
  transaction. The client receives `mission_transition` plus `mission.transitioned` with
  `snapshot_required: true`.
* **Failure commits nothing** (`fail_mission`): the history records the attempt; the mission
  stays replayable; the phase is `failed` until a retry completes it.
* **Ending a mission** — `authorization` missions (Earth Command) end when the player
  authorizes at the gate with every requirement met; `simulation_concluded` missions (LUNA-01)
  end when the simulation concludes, completing on success/partial/exceptional tiers and failing
  on `mission_failed`/`critical_failure`.

## Earth Command (phase 1)

Locations: observation deck, mission control, engineering bay, science laboratory, training
center, crew quarters, medical bay, spacecraft hangar, launch access airlock (locked until
authorization). Flow:

1. Session created → the player is on the observation deck; the clock is paused until the first
   zone entry.
2. Free exploration (telescope discovery, dosimetry insight, crew cues).
3. The hidden breaker fault drops power bus B → `incident.started`, clock `DECISION_PAUSED`,
   Maya/Jay intents, insight `power.generation_vs_demand`.
4. Investigate (`system.inspect` power bus B → stage `investigating`, repair trade-off cue).
5. Act (shed loads, reroute spacecraft energy, repair with a breaker spare from the locker).
6. The engine computes the consequence; the incident resolves (or escalates on
   `critical_load_lost` / `battery_critical`); facts (`critical_load_lost`, `reserve_depleted`,
   `load_shed`) are recorded per tick.
7. Resolution makes LUNA-01 `inspection_ready`.
8. Inspect power, life support, comms, radiation protection and the cargo hold; install the
   radiation shelter liner; load two water tanks and a habitat spares kit (mass-budgeted);
   keep ground support on until the spacecraft battery reaches 45 kWh.
9. `mission.authorize` at the LUNA-01 gate (requirements: `station_power_nominal`,
   `spacecraft_inspected`, `radiation_protection_installed`, `required_cargo_loaded`,
   `spacecraft_charged` — phrased over observable state so the gate never hints at the hidden
   incident).
10. Completion commits evidence (incident resolved, critical loads protected, reserve
    protected, manifest checked, launch authorized), derives capability stages, grants
    `cert.earth_command.station_operations`, carries the cargo and transitions to LUNA-01.

`tests/test_game_api.py::test_earth_command_end_to_end_through_the_api` runs exactly this flow
through the production API, then saves, disconnects, restarts the server process on the same
database and verifies the restored state is identical.

## LUNA-01 (phase 2)

The protected LUNA-01 v0.2.0 scenario under the server clock (1 h per tick, 0.25 ticks/s in
realtime, ×4 accelerated, at most 24 ticks settled at once). The ASTERIA world maps habitat,
shelter, solar field, comms relay, rover depot and science sites onto the scenario's consumers,
components and opportunities; the radiation storm and water-processor fault are hidden incidents
that start only when their simulation events fire. Completion evidence covers lunar-night
power, radiation sheltering within dose, rover traverse, lunar science, data return and outpost
sustainment.

## Mars

`MARS_01` has no missions and no invented science. It is gated by the readiness profile
`mars_01_human_mission` (`content/data/readiness.yaml`): twelve explicit gates across transport,
long-duration habitation, life support, power, radiation protection, communications, autonomy,
robotics, logistics, surface systems, entry/descent/landing and return capability; ten are
critical. A percentage (`gates_met / gates_total`) is always shown next to the list of missing
critical gates and **never** unlocks anything: any missing critical gate keeps the profile
locked with `MARS_MISSION_LOCKED` and the missing capability ids (tested with every non-critical
gate met and percentage ≥ 90 %). Adding Mars later means authoring missions/content for the
phase and the evidence that reaches `MARS_CERTIFIED`; the architecture does not change.

## Content versions

`manifest.yaml` declares `content_id`, `content_version` and `compatible_from`. Content is
validated at startup and in tests (schema + cross-references: every id referenced anywhere must
exist; incidents never leak into the client catalog). See
[SAVE_RESTORE.md](SAVE_RESTORE.md#content-versions) for the migration strategy.
