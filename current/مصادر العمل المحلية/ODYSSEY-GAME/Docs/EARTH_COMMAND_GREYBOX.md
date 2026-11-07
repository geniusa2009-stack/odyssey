# Earth Command verification greybox — specification

> UNREAL_EDITOR_VERIFICATION_REQUIRED. The map does **not** exist yet. Nothing the editor script
> produces is accepted until reviewed in the editor (§33).

## Single source: the map definition

`Content/Systems/Greybox/L_EarthCommand_Slice.layout.json` defines every area, door, anchor,
zone, system actor, light (and which backend object it follows, under which rule) and crew
placeholder. It is consumed by:

| Consumer | Uses it for | Status |
|---|---|---|
| `Tools/Editor/build_earth_command_greybox.py` | builds the map (contains no layout of its own) | UNREAL_EDITOR_VERIFICATION_REQUIRED; dry-run against a stub passes |
| `Tools/SemanticIds/generate_registry.py` | `RequiredInSlice` = bound in the map; `Binding` = actor label | run |
| native tests (`VerificationMapScope`, `RegistryMatchesMapDefinition`, `PowerIncidentStrategiesAreFullyMapped`, `ShedRoomsReactAndRestore`) | scope, ids, both incident strategies, room reactions | run, pass |
| live harness | evaluates the map's light rules on real backend state | run, pass |

**Exact target:** `/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice`, Outliner folder
`EarthCommandGreybox/…`. The script refuses an existing map unless `REBUILD = True` (then it
deletes only that folder), and refuses any area outside `allowed_areas`.

## Areas (exactly seven)

Units: cm, origin at the corridor's west end. Doors 260 cm high.

| Area | Extent (x; y) | Height | Backend location | Contents |
|---|---|---|---|---|
| Observation Deck | -1600..0; -900..900 | 600 | `earth.command.observation_deck` | 14 m window opening (west), lunar telescope, player kit, new-campaign spawn |
| Main Corridor | 0..4000; -200..200 | 320 | — (Unreal-only) | doors N → Mission Control (x 1400), Training (2700); S → Engineering (2500), Laboratory (3650); E → Hangar |
| Mission Control | 800..2000; 200..1400 | 420 | `earth.command.mission_control` | console bank |
| Training | 2200..3200; 200..1200 | 380 | `earth.command.training` | **training simulator** (`earth.command.training.simulator`), 2 ceiling lights + simulator indicator |
| Engineering | 1800..3200; -1600..-200 | 420 | `earth.command.engineering` | **power console** (power bus B), battery, thermal plant, air handling, water systems, spares locker; 4 ceiling lights + warning light |
| Laboratory | 3350..3950; -1200..-200 | 380 | `earth.command.laboratory` | **sample analyzer** (`earth.command.laboratory.sample_analyzer`), 2 ceiling lights + analyzer indicator |
| Hangar Entrance | 4000..4800; -600..600 (+ floor beyond) | 500 | `earth.command.hangar` | opening onto LUNA-01 (placeholder volume) |

Training and Laboratory are minimal: a room shell, one anchor, one zone, the one backend load and
its lights. No props, no final materials. Each backend location has one
`AOdysseySemanticAnchor` and one `AOdysseySemanticZone` (inset from the walls, 0.35 s dwell).

## Both incident strategies are playable

The backend accepts two strategies and neither is "correct" — it computes the consequence
(`Tests/Data/earth_command_power_incident_strategies.json`, transcribed from the backend's tests):

| Strategy | Path | Consequence (backend) |
|---|---|---|
| `repair_at_once` | Engineering → inspect bus B → repair | incident resolves; station stability objective fails |
| `shed_loads_first` | Engineering → inspect → Training: simulator `off` → Laboratory: analyzer `off` → Engineering → repair | stability protected; training/lab work paused |

Afterwards the player may restore both loads (`system.set_mode mode=nominal`).

## Lights follow the backend (presentation rules)

Rules live in the map definition and are evaluated by `odyssey::presentation::Evaluate` (the same
function in Unreal and in the tests). Backend values: `power` powered|off, `mode`
off|eco|nominal|boost, `status` operational|offline|damaged.

| Rule | Used by | Multipliers (unlisted = 1) | Shed (`off/off/offline`) | Restored (`powered/nominal/operational`) |
|---|---|---|---|---|
| `room_load` | Training & Laboratory ceiling lights → their load | power off 0.35, mode eco 0.75 | **0.35** (dim standby, still lit) | 1.0 |
| `equipment` | simulator / analyzer indicator | power off 0, mode eco 0.5, status offline 0, damaged 0.4 | **0** (dark) | 1.0 |
| `bus_room` | Engineering ceiling lights → power bus B | power off 0.25, status damaged 0.5, offline 0.25 | — | 1.0 |
| `warning` | Engineering warning light → power bus B | on while an active incident involves the bus | — | off |
| `static` | other rooms | — | — | — |

Shedding one room never changes the other's lights (tested). Restoring returns exactly the
authored intensity because intensities are always recomputed from the backend's current values.

## Sightlines and flow

* Spawn on the Observation Deck facing the window; turning around frames the corridor and the
  hangar light at its end.
* Corridor order east-bound: Mission Control (N), Engineering (S), Training (N), Laboratory (S),
  Hangar. Training and Laboratory sit between Engineering and the hangar, so the load-shedding
  route is a short loop off the corridor.
* Inside Training/Laboratory the load faces the door; the ceiling lights above it are what dims.

## Crew placeholders

Mannequins at Mission Control (Maya), Engineering (Omar), Hangar Entrance (Sofia), Observation
Deck (Jay); semantic identity = binding id; StateTree `ST_CrewSlice` (editor asset) reads
`UOdysseyCrewStateComponent`.
