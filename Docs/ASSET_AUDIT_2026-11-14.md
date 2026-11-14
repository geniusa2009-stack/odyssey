# ODYSSEY asset audit — 2026-11-14

Reference pool audited before the space-experience pass: repo content, `ArtSource/`, the handoff
packs, the Replit prototype and the user's uploads (`~/Downloads`). Duplicates were grouped by
sha256, triangle count, glTF structure and a rendered visual check.

## Canonical sources

| Object | Canonical | Duplicates / superseded | Notes |
|---|---|---|---|
| Power Console | `ArtSource/OdysseyProduction/SourceConsole/OD_ENG_PowerConsole_ScalePivotFixed.glb` (sha 12160be9) | `~/Downloads/OD_ENG_PowerConsole_ScalePivotFixed.glb` (identical); `sample_2026-11-13T194213.115.glb` (same 293,949-tri mesh before scale/pivot fix) | Already imported (`Engineering/Production/ConsoleHero`, `ConsoleClean`). |
| Holo projector base | `Central Projector Core-f3d6287f….glb` | `Futuristic Command Console-76694354….glb` + `.fbx` (same object, two formats), `Futuristic Energy Core-4a608b61….glb` (near-identical variant) | AI image-to-3D, 500k tris, 1 baked 4K material. Branded ODYSSEY plates → Mission Control holo table. |
| Holo ring | `Futuristic Energy Ring-b0e0039f….glb` | — | Optional ring element above the projector. |
| Training Simulator | `…Futuristic Training Simulator-1-4e838ad5….glb` | `… (1).glb` (byte-identical) | AI, 500k tris; baked text partly garbled. Pack `OD_TRN_TrainingSimulator` remains the clean reference. |
| ORION Terminal | pack `OD_SYS_ORIONTerminal.glb` | `…Futuristic Command Terminal-1-3221b728….glb` | AI version has garbled screen text → reference only. |
| Server Rack | pack `OD_SYS_ServerRack.glb` | `sample_2026-11-13T221902.522.glb` | AI rack → reference only. |
| Inspection Drone AID-03 | `OD_DRONE_Inspection_AID-03 (1).glb` (newest, 08:03) | `OD_DRONE_Inspection_AID-03.glb` (03:24, same structure), 3 × `.obj`/`.mtl` exports | Structured three.js export, ODYSSEY material names, 33k tris. |
| Drone Docking Station | `OD_DockingSystem.glb` | `OD_DockingSystem.obj/.mtl` | Structured, branded, 44k tris. |
| Station Sliding Door | `SM_ODY_StationSlidingDoor.glb` | `.obj/.mtl`; pack `OD_ENV_SlidingDoor.glb` (earlier procedural version); `مخطط باب المحطة الانزلاقي ODYSSEY.png` ×2 (identical blueprint) | Structured, 7k tris. |
| Handoff references | `ODYSSEY_SESSION_SCRATCH_2026-11-14/handoff/…/References` (15 PNG) | `ODYSSEY_Handoff_{1..4}_of_4 (1).zip` == `ODYSSEY_Handoff_{1..4}_of_4.zip` (sha-identical pairs) | Equipment design references only. |

## Branding (from the Replit prototype)
Wordmark `ODYSSEY` (Chakra Petch 700, graphite on light UI), subtitle in IBM Plex Mono with wide
tracking (`EARTH COMMAND / ENV PROTOTYPE 0.1`), mark = ion-blue outlined diamond on a graphite tile.
No logo animation, planet, space or vehicle asset existed anywhere in the pool.

## Gaps filled by the space-experience pass
Earth, Moon, Mars, starfield, transit vehicle, animated logo, front-end / travel flow — see
`Docs/SPACE_EXPERIENCE.md`.
