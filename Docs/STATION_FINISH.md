# Earth Command station finish pass (2026-11-14)

Unreal-only presentation over the validated greybox: no semantic id, binding, backend contract or
protocol fixture changed. Everything placed by the pass carries the tag `OdysseyRoomFinish` (rooms,
doors, hologram) or `OdysseyImportedDressing` (earlier imports) and is rebuilt idempotently by:

```
py Tools/Editor/Production/build_room_finish.py      # kits, Mission Control, Training, corridor, doors, hologram
py Tools/Editor/Production/import_station_glbs.py     # holo projector, simulator, drone dock / drone
```

## Mission Control (x 800–2000, y 200–1400, h 4.2 m)
* Room kit (`SM_KIT_MCC_*`): kick / ion trim / aerospace-white panels / ribs every 2 m, vents, cornice,
  door header, 1 m floor plates, 2 m ceiling bays with beams.
* Centrepiece: the projector table (Nanite) with **`AOdysseyHoloTable`**, a floor inlay ring (graphite
  field, ion light line, aluminium seams) and a suspended light halo with a key light.
* Operations: pack `OD_MCC_MainConsole` (three segments) + three `OD_MCC_MissionControlChair`
  (`Sys_Consoles` keeps its semantic binding and collision; its proxy mesh is hidden), main / systems /
  comms wall displays, three server racks, ORION terminal, utility panel, ventilation module,
  four ceiling fixtures, corridor signage.

### Holographic mission table — `AOdysseyHoloTable` (module OdysseyWorld)
| State | Content |
|---|---|
| OFF | projection dark |
| BOOT | power ramp, scan disc sweeps up through the volume |
| EARTH OVERVIEW | Earth hologram (planet texture through `M_ODY_Hologram`), station ring + marker, vehicle in parking orbit |
| MISSION PLANNING | Earth / Moon / Mars system, lunar orbit ring, pulsing destination selection (Moon, then Mars) |
| TRAJECTORY | animated transfer arc (instanced beads) to the selected destination, vehicle staged at departure |
| SIMULATION | vehicle flies the arc repeatedly, faster bead flow |
| INCIDENT | red alert colouring, pulsing station marker, label from the backend incident (`GetIncidents`, read-only) |
| RESOLVED | colour returns to ion, "station systems nominal", then overview |

Auto program: Boot → Overview (12 s) → Planning (10 s) → Trajectory (9 s) → Simulation (14 s) → loop;
backend incidents interrupt it. All content is separate components with dynamic material parameters
(nothing baked into the projector mesh). Niagara was not needed: every effect is a mesh + material
parameter, which keeps it deterministic and cheap.

## Training (x 2200–3200, y 200–1200, h 3.8 m)
Room kit, simulator safety zone (amber hazard border) + "SIMULATOR ZONE – KEEP CLEAR" floor marking,
instructor station (scaled main console + chair, facing the simulator), monitoring desk with session
and biomedical displays, storage crates, utility panel, four fixtures, corridor signage. The simulator's
semantic console (`Sys_TrainingSimulator`) is unchanged.

## Corridor
Finished with the same kit (walls, ribs, floor, ceiling, cornice, door headers) and six fixtures.
`Odyssey.Slice.Engineering` walks it and still passes.

## Sliding doors — `AOdysseySlidingDoor` (module OdysseyWorld)
`SM_ODY_StationSlidingDoor.glb` is split offline into frame / leaf L / leaf R GLBs
(`ArtSource/OdysseyImports/Split`) and imported combined. Presence volume (±2.6 m through the doorway)
opens the leaves with an eased 0.85 s stroke, holds 1.2 s after the last pawn leaves, then closes.
Leaves sit inside the wall thickness and slide into it (pocket door, no clipping); the frame uses
complex collision so the opening stays walkable. Status strips: ion = ready, amber = moving,
red (pulsing) = locked (`SetLocked`). Placed on the Mission Control and Training doorways; the
Engineering doorway keeps its validated open frame.

## Engineering
Keeps the production pass already in the map (architecture modules, service plant, power console,
Bus B cabinet, equipment) plus the drone dock and inspection drone. Lighting stays driven by the
`bus_room` / `warning` presentation groups (validated incident behaviour), so no extra non-group fill
lights were added.

## Validation
* `-OdysseyStationTour` (game, backend running): 15 screenshots of the rooms, every hologram state,
  doors closed / open, Engineering → `Saved/Odyssey/StationTour`, copies in `Docs/Validation/Station`.
* `Odyssey.Slice.Engineering`: passes with the finished corridor, doors and rooms.

## Tools / dependencies added
| Item | Use | Runtime dependency |
|---|---|---|
| numpy + Pillow (Python venv, dev only) | planet / starfield / station texture generators | none |
| Engine Roboto / Droid Sans Mono fonts (Apache 2.0, ship with UE) | text in generated display / sign textures | none |
| Interchange pipeline assets `PL_ODY_CombinedStaticMesh` | combined-mesh GLB import | none |
No new engine plugins were enabled.
