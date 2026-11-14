# Imported production sources (canonical picks, 2026-11-14)

Canonical versions chosen in `Docs/ASSET_AUDIT_2026-11-14.md` (duplicates / superseded copies are listed there).

| File | Source upload | Kind | Unreal import |
|---|---|---|---|
| `OD_MCC_HoloProjectorCore.glb` | `Central Projector Core-f3d6287f….glb` | image-to-3D, 500k tris, baked PBR | `/Game/Earth/EarthCommand/Imported/HoloProjectorCore` → Mission Control holo table |
| `OD_TRN_TrainingSimulatorHero.glb` | `…Futuristic Training Simulator-1-4e838ad5….glb` | image-to-3D, 500k tris, baked PBR | `/Game/Earth/EarthCommand/Imported/TrainingSimulator` → Sys_TrainingSimulator visual |
| `OD_ENG_DroneDockingStation.glb` | `OD_DockingSystem.glb` | structured ODYSSEY kit (three.js export) | `/Game/Earth/EarthCommand/Imported/DroneDock` → Engineering |
| `OD_DRONE_InspectionAID03.glb` | `OD_DRONE_Inspection_AID-03 (1).glb` (newest) | structured ODYSSEY kit | `/Game/Earth/EarthCommand/Imported/InspectionDrone` → Engineering dock |
| `SM_ODY_StationSlidingDoor.glb` | `SM_ODY_StationSlidingDoor.glb` | structured ODYSSEY kit | imported for the door pass (not placed yet: panels need an open/close actor) |

All are glTF (Y-up, metres); Unreal's Interchange importer converts to Z-up centimetres. Scale and
placement are applied by `Tools/Editor/Production/import_station_glbs.py`.
