# World Semantic State

The backend models the world as **meaning**, never geometry. Content:
`content/data/worlds/*.yaml`; state: `TimelineGameState`; views: `app/game/world/views.py`.

## Stable, human-readable ids

`<world>.<area>[.<thing>…]`: `earth.command.engineering.power_bus_b`,
`earth.command.hangar.luna01.cargo_hold`, `luna.asteria.shelter.module`. Ids are content, never
generated, and never change between sessions or versions within a content major version
(content validation checks every reference; the fuzzer asserts every id in a snapshot exists in
the content). Unreal maps ids to actors and world anchors in its own configuration.

## Concepts

| Concept | Where | Notes |
|---|---|---|
| world | `worlds/<id>.yaml` | Earth Command, ASTERIA (LUNA-01) |
| region | `regions` | grouping only |
| location / zone / facility / site | `locations` | `kind`, `access` (`open`/`locked`), `unlock_when`; the player's semantic location is one of these |
| object | `objects` | `kind`: system, subsystem, interactable, container, poi, vehicle, infrastructure, … |
| interactions | per object | the semantic actions it supports, parameters, requirements (with safe reasons), consumption, simulation decisions, game-side effects, `once` |
| binding | per object | which simulation consumer/component/rover/opportunity it reflects |
| incidents | per world | **hidden** until triggered; stages in priority order, facts, start/stage effects, pause-on-start |
| discoveries | per world | science/resource/terrain/historical artifact/engineering observation/mission anomaly |

## Object state

Stored (timeline-local): `access` (`open`, `restricted`, `inspection_ready`, `locked`), `known`
(hidden objects are not in snapshots until revealed), `operational`, `inspected`. Derived on
every read from the simulation binding:

* `status`: `operational`, `degraded`, `damaged`, `maintenance`, `offline`, `nominal`
  (component health and maintenance; consumer supply)
* `power`: `powered`, `partial`, `unpowered`, `off` (consumer mode and supply ratio)
* `mode`: the consumer's operating mode
* `charge_kwh` for vehicles bound to the engine's rover battery
* installed `modules` and their state; `infrastructure_state` (below)
* `interactions[]` with `available` and a safe `reason` when not

Mission relevance, criticality and tags are content. Ownership is implicit (one commander per
session in Phase 5).

## Player semantic location

`player_location` plus `visited`. It changes only through `world.zone_entered` (and mission
start). Spawn transforms are Unreal's: restore the exact local spawn from the anchor
configuration for the stored semantic location or checkpoint `location`.

## Incidents

An incident starts when its trigger holds (usually a simulation event having fired); before that
it is absent from every payload. Its current stage is the first whose condition holds; terminal
stages end it. Facts (e.g. `critical_load_lost`) are observed **per simulated tick** during clock
advancement, so transient conditions between turns are never missed. Stage effects update the
world (Earth Command's resolution makes LUNA-01 `inspection_ready`), crew intents and insights.
`pause_clock_on_start` puts the clock in `DECISION_PAUSED` at the exact tick it starts.

## Infrastructure

Infrastructure objects (`infrastructure_type`) have a derived state:

| State | Rule |
|---|---|
| `planned` | none of the required module categories installed |
| `under_construction` | some, but not all, required modules installed |
| `offline` | in maintenance, or power-dependent and unpowered/off, or switched off |
| `damaged` | bound component health below the damaged threshold |
| `degraded` | component degraded or partial power |
| `operational` | otherwise |

Infrastructure may depend on power, communications, logistics, capabilities and installed
modules (type fields `depends_on_*`, `requires_capabilities`, `requires_modules`).

**Persistence.** At a successful mission completion the state, installed modules, mission and
attempt of every infrastructure object of that world are recorded in campaign meta
(`campaign.infrastructure`, event `infrastructure.changed` with `persistent: true`). A later
mission in that world with `inherit_infrastructure: true` starts from those records (modules as
left, offline/damaged objects non-operational) instead of the authored state; replays of a
historical mission (LUNA-01) start from the authored state. Failed missions record nothing.

## Discoveries

Idempotent: recorded at most once per timeline (`once` interactions, `record_discovery`),
with what, where (semantic location), mission, tick and source; pending on the timeline and
committed to the campaign once at mission completion (so a rewind drops a pending discovery and
re-discovering it cannot duplicate it). The view lists what it unlocks: knowledge (insights,
immediately) and, for some discoveries, *pending* capability evidence (the LUNA-01 regolith core
contributes `evidence.science.surface_sample_collected`) that counts only when the mission
completes. A discovery never sets a capability stage directly.

## What is never in world state

Meshes, transforms, materials, animation, audio, physics, lighting, camera, pathfinding, NPC
positions.
