# Gameplay ↔ Backend Boundaries

The rule: **Unreal renders and simulates the body; the backend decides the mission.**

## Unreal owns (the backend never sees it)

Player movement and transforms, camera, animation (including crew idle/work/facial animation),
collision, local physics, rover driving physics, visual effects, audio, character locomotion,
NPC pathfinding, Smart Objects, StateTrees, physical interaction feedback, rendering, visual
transitions, cinematics, spawn transforms (from its own world-anchor configuration), lighting
and every art decision (colour, materials, Niagara, MetaHumans).

## The backend owns

Mission truth and the deterministic simulation; campaign progression; objectives and
consequences; incidents; the server clock; world *semantic* state; inventories, cargo and mass
budgets; hardware modules and compatibility; persistent infrastructure; discoveries and
knowledge; capability qualification and certification; Mars readiness; Future Lens, Black Box,
Rewind, Mission DNA and the Engineering Profile; authoritative saves.

## What crosses the boundary

| Direction | What | Never |
|---|---|---|
| Unreal → backend | semantic actions with stable ids (`world.zone_entered` + `earth.command.engineering`, `system.set_mode` + target + `mode`), requests for reads, clock-mode *requests*, optional world-anchor id for logs | coordinates, transforms, velocities, per-frame updates, animation states, resource values, completion flags, quantities, repair results, unlocks |
| backend → Unreal | snapshot (semantic state), events (deltas), decided results with safe reasons, crew cue ids + one-line text + priority, semantic hints (powered/offline/degraded, warning levels) | hidden future events or schedules, seeds, engine internals, raw database ids, art direction ("make it cyan", "play animation X", "spawn particle Y") |

A movement-level fact enters the backend only when it is *meaningful*: the player entered the
engineering zone (it starts the clock and makes engineering interactions available), the player
is at the hangar (needed to install a module). There is no "player position" endpoint.

## Validation and trust

The client requests; the backend decides. Every command is validated against the mission,
campaign phase, timeline, world state, target existence and visibility, access, the player's
semantic location, parameters, requirements, resources, `once` rules, capabilities and module
compatibility (`app/game/actions/planner.py`), then dry-run on copies of the state before
anything authoritative changes. Requests are closed schemas (unknown fields → 422); actors
other than the commander are not controllable in Phase 5.

## Crew

Maya (Systems Engineer), Omar (Planetary Scientist), Sofia (Life Support Specialist) and Jay
(Mission Operations) exist in the backend only as semantic state: role, specialty, current
*intent* (e.g. `repairing_power_bus_b`), incident involvement and the simulation crew they map
to. Unreal decides where they stand and how they move.

### Contextual cues (minimal text)

Cues are short, prioritized barks (`content/data/narrative.yaml`): speaker, cue id, priority,
`once` or `cooldown_ticks`, a context condition and **one** line plus a `message_key` for
localization. The reactor fires eligible cues on a turn and records them in
`world.recent_cues` (bounded) and as `crew.cue` events; Unreal decides when and how a cue is
physically presented — or whether it is skipped. There are no dialogue trees and no tutorials.

## Earth Command uses the real engine

Earth Command is a second scenario for the same engine (educational abstraction, all numbers
gameplay parameters, `provisional: true`): the station's main feed is the engine's generation
source routed through *power bus B* (component `power_bus_b`), the LUNA-01 spacecraft's ground
battery is the engine's rover battery charged by `hangar_ground_support`, life-support stocks
are sized so they never bind on Earth. Priority load shedding, battery reserve, critical vs
non-critical loads, thermal coupling and maintenance (repairs take the component offline) are
the engine's equations — no second "game" simulation exists.

The power incident is deliberately small and real: a scheduled breaker fault (unforeseeable,
so hidden from Future Lens and from every payload until it happens) drops bus B; the player
investigates and chooses. There is no correct answer: repairing immediately takes the bus
offline and costs station stability; shedding the training simulator and the lab first protects
stability at the cost of the work those loads were doing; rerouting spacecraft energy to the
station buys reserve at the cost of launch charge. The engine computes each consequence
(`tests/test_game_api.py::test_strategies_have_different_costs_through_the_api` checks the
first two).

## Determinism

Given the same content version, session seed and recorded command times the result is
identical: the clock is derived from recorded server time, the simulation is deterministic,
and the game core is pure. Tests and the fixture recorder inject a fake clock.

## What the backend deliberately does not do

* No XP, levels, loot, rarity or currency.
* No dialogue engine, quiz or "correct answer".
* No 3D/shipyard geometry: vehicles are slots, mounts, buses, ratings and mass budgets.
* No Mars simulation: Mars has gates, not invented science ([CAMPAIGN_MODEL.md](CAMPAIGN_MODEL.md#mars)).
* No background workers: time advances when a session is processed.
