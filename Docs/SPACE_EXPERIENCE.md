# ODYSSEY space experience — front end, Earth / Moon / Mars, OTV-1 transit

Presentation layer only. The backend owns mission truth; nothing here sends or invents semantic
intents. Travel between bodies is Unreal-side storytelling and navigation, ending (for Earth) in the
Earth Command station map where the backend-driven game runs.

## Flow
```
startup (GameDefaultMap = L_Odyssey_SolarTransit)
  └─ black hold while shaders warm up
  └─ animated ODYSSEY logo (Intro)                    any key skips to the outro
  └─ MENU over the Earth hero shot
       ├─ BEGIN MISSION   → fade → L_EarthCommand_Slice (station, backend session)
       ├─ SOLAR TRANSIT   → NAVIGATION in Earth parking orbit
       │     A/D or 1-3 destination · ENTER launch · C camera · E descend (at Earth) · ESC menu
       │     launch → transfer window alignment → departure burn → coast → flip → orbit insertion
       └─ EXIT
```
Gamepad: d-pad, A confirm, B back, Y camera, X descend.

## Content
| Asset | Path | Source |
|---|---|---|
| Map | `/Game/Space/Maps/L_Odyssey_SolarTransit` | `Tools/Editor/build_space_experience.py` |
| Earth / Moon / Mars maps (albedo, normal, masks, clouds) | `/Game/Space/Textures` | `ArtSource/OdysseySpace/Source/generate_space_textures.py` → `ArtSource/OdysseySpace/Textures` (4K, starfield 8K) |
| Planet / atmosphere / sky / sun meshes | `/Game/Space/Meshes/SM_ODY_*` | `Tools/Editor/odyssey_space_geometry.py` |
| OTV-1 "Meridian" hull, plumes, RCS | `/Game/Space/Meshes/SM_OTV_Meridian_*` | `odyssey_space_geometry.transit_vehicle()` etc. |
| Materials | `/Game/Space/Materials` | `M_ODY_PlanetSurface` (day/night, city lights, drifting clouds, ocean gloss, limb haze), `M_ODY_PlanetAtmosphere` (additive rim + terminator scattering), `M_ODY_Starfield`, `M_ODY_SunDisc`, `M_ODY_EnginePlume`, `M_ODY_NavLight`, hull instances of `M_ODY_HardSurface` |

Rebuild everything: `py Tools/Editor/build_space_experience.py` in the editor (or `ODY_STEPS="map"` /
`"materials+map"` passed as an init global to rebuild only part). Regenerate textures with
`python generate_space_textures.py --size 4096 --stars-size 8192` (numpy + Pillow).

## Code (module `OdysseySpace`)
| Class | Role |
|---|---|
| `AOdysseyCelestialBody` | surface + atmosphere shell, spin, parking orbit, live `SunDirection` to materials, navigation data (real radius / distance) |
| `AOdysseyTransitVehicle` | hull, three plumes (Thrust), engine light, RCS pulses, navigation strobes |
| `AOdysseyTransitDirector` | transfers (Bezier kept clear of all bodies, arc-length parameterised, trapezoidal speed profile, 180° flip before the retro burn), camera language (menu hero, orbit vista, planet view, 4-shot transfer sequence with blends), sky and sun kept on the camera, telemetry |
| `UOdysseyLogoWidget` | animated logo (Intro 6.8 s / Sting 3.2 s), code-drawn, resolution independent |
| `UOdysseySpaceHUDWidget` | brand badge, main menu, transfer planner, telemetry, arrival banner, letterbox, fades |
| `AOdysseySpaceGameMode` / `AOdysseySpacePlayerController` | flow, input, `-OdysseyCapture` validation tour, `-OdysseySkipIntro`, `OdysseyTravel <i>` exec |

Scale is a compressed "diorama": Earth radius 10 km in world units, Moon and Mars at true size ratios,
distances compressed (Moon ~11.5 R⊕, Mars ~40 R⊕) so transfers read in 17–24 s. The navigation display
and telemetry use real distances (384,400 km, ~225 M km) and mission times (3.1 days, ~207 days).

## Verification
* `Odyssey.Space.Flow` (automation, no backend):
  `UnrealEditor Odyssey.uproject /Game/Space/Maps/L_Odyssey_SolarTransit -game -nullrhi -unattended -nosound -ExecCmds="Automation RunTests Odyssey.Space.Flow" -TestExit="Automation Test Queue Empty"`
* Visual tour: `UnrealEditor Odyssey.uproject /Game/Space/Maps/L_Odyssey_SolarTransit -game -windowed -ResX=1600 -ResY=900 -OdysseyCapture`
  → `Saved/Odyssey/SpaceCapture/SPACE_01..15_*.png`, then quits.
* The Engineering slice test now names its map explicitly (the default map is the front end):
  `UnrealEditor Odyssey.uproject /Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice -game -nullrhi … Odyssey.Slice.Engineering`

## Results (2026-11-14, UE 5.8.4, Apple M3 / 8 GB)
| Check | Result |
|---|---|
| `OdysseyEditor` build with `OdysseySpace` (2 parallel actions) | succeeded |
| `Odyssey.Space.Flow` | **Success**, 0 errors (warnings: backend readiness ping, no backend needed here) — Moon arrival at 1.350 R (parking orbit 1.350), Mars at 1.220 R (1.220) |
| `-OdysseyCapture` tour | 15/15 screenshots, 0 material compile failures, ~85 s |
| `Odyssey.Slice.Engineering` (with station imports placed) | **Success**, 41 checks, 0 errors (1 benign missing-save warning) |
| Native protocol core | 26/26 cases, 959 checks |
| Backend snapshot | 336 files byte-identical to the recorded manifest |

### Known limits / next steps
* Planet maps are procedural (4K); a hero close-up of Earth would benefit from 8K albedo/clouds.
* The first launch compiles shaders (the front end holds black until compilation settles).
* `SM_ODY_StationSlidingDoor` is imported but not placed: it needs an open/close door actor so the
  Engineering traversal stays clear.
* Mission Control and Training rooms are still greybox shells around the new hero props.
