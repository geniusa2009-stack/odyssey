# Earth Command greybox — specification

> UNREAL_EDITOR_VERIFICATION_REQUIRED. The map does **not** exist yet. This is the specification
> that `Tools/Editor/build_earth_command_greybox.py` implements; nothing it produces is accepted
> until reviewed in the editor.

**Exact target:** `/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice` — Outliner folder
`EarthCommandGreybox/…`. The script refuses to touch an existing map unless `REBUILD = True`, and
then deletes only actors inside that folder.

## Areas (Phase 6 §16: only these)

Units: cm. Origin at the corridor's west end. Doors 300×260 (corridor ends) / 240×260 (rooms).

| Area | Extent (x, y) | Height | Backend location | Contents |
|---|---|---|---|---|
| Observation Deck | -1600..0, -900..900 | 600 | `earth.command.observation_deck` | 14 m window opening (west), lunar telescope, player kit, spawn anchor (start location of a new campaign) |
| Main Corridor | 0..4000, -200..200 | 320 | — (Unreal-only) | ceiling lights every 8 m; doors N (Mission Control), S (Engineering), E (Hangar) |
| Mission Control | 800..2000, 200..1400 | 420 | `earth.command.mission_control` | console bank (`mission_control.consoles`) |
| Engineering | 1800..3200, -1600..-200 | 420 | `earth.command.engineering` | **power console (power bus B)** facing the door, station battery, thermal plant, air handling, water systems, spares locker; 4 ceiling lights + 1 warning light wired to power bus B |
| Hangar entrance | 4000..4800, -600..600 (+ hangar floor beyond) | 500 | `earth.command.hangar` | wide opening onto LUNA-01 (placeholder volume, 9 × 4.5 × 7 m) under a high light |

Each backend location has one `AOdysseySemanticAnchor` (arrival transform, facing into the room)
and one `AOdysseySemanticZone` (inset from the walls so doorways do not flicker; 0.35 s dwell).

## Sightlines and flow

* Spawn on the Observation Deck facing the window: first image is space, not a corridor.
* Turning around frames the corridor's full length with the hangar light at its end (the goal).
* Engineering's door is on the corridor's south side, opposite Mission Control's: the player
  passes Mission Control (crew activity visible) before reaching Engineering.
* Inside Engineering the power console faces the door; the room lights it controls are visible
  from the doorway, so the dimming reads immediately.

## The incident in the world

The backend decides everything; the map only presents:

| Backend state | Presentation |
|---|---|
| `power_bus_b` `status: damaged` / power degraded | Engineering ceiling lights blend to 35–50 % |
| incident active involving `power_bus_b` | Engineering warning light on (tag `OdysseyWarning`) |
| clock `DECISION_PAUSED` | one-line HUD alert; crew stop and turn to Engineering (StateTree) |
| repaired / incident resolved | lights blend back; warning off |
| LUNA-01 `access: inspection_ready` | hangar presentation (Blueprint hook) |

## Strategy note (needs a decision)

The backend accepts two incident strategies, and neither is "correct": **repair at once** (works
within these five areas; costs station stability) or **shed training and laboratory loads first**
(needs `earth.command.training` and `earth.command.laboratory`). Those rooms are not among the
five Phase 6 areas, so the script leaves them out (`INCLUDE_LOAD_SHED_STUBS = False`). Turning the
flag on adds a door-sized Training stub off the corridor. The Laboratory stub is not scripted yet.

## Crew placeholders

Mannequins at Mission Control (Maya), Engineering (Omar), Hangar entrance (Sofia), Observation
Deck (Jay). Their semantic identity is the binding id; the backend's crew view
(intent/location/incident involvement) feeds `UOdysseyCrewStateComponent` for the StateTree
`ST_CrewSlice` (activities: operate console, inspect equipment, sit, walk between points,
observe window — authored in the editor with Smart Objects).
