# ODYSSEY — Earth Command Asset Pack

Fifteen original, game-ready hard-surface props for ODYSSEY Earth Command. Each one is real 3D geometry in a
GLB (glTF 2.0 binary) file. Every prop has named, animatable node hierarchies, shared PBR materials, exact
mounting envelopes and pivots, and a spec in JSON and Markdown. The approved reference PNGs were used only
as visual reference. They are not used as geometry or textures.

| # | Asset | W x H x D (m) | Pivot | Tris | Movable / interactive nodes |
|---|---|---|---|---|---|
| 1 | `OD_ENG_PowerConsole` | 1.80 x 1.25 x 0.90 | floor | 16.2k | ServicePanel, 3 knobs, 3 faders, 3 toggles, E-stop, buttons |
| 2 | `OD_ENG_PowerBusB` | 1.20 x 2.20 x 0.60 | wall_base | 9.2k | AccessDoor, 3 main breakers, 8 MCB toggles, 2 toggles |
| 3 | `OD_TRN_TrainingSimulator` | 3.20 x 2.80 x 3.80 | floor (plinth) | 13.9k | SimSeat (swivel), knob, 3 faders, E-stop, buttons |
| 4 | `OD_LAB_SampleAnalyzer` | 1.60 x 1.70 x 0.90 | floor | 10.1k | ChamberDoor, CartridgeTray, SampleArea, MaintenancePanel, knob, E-stop |
| 5 | `OD_MCC_MainConsole` | 4.80 x 1.30 x 1.60 | floor | 19.5k | per segment: knobs, mode levers, E-stop, buttons; 8 displays |
| 6 | `OD_ENV_SlidingDoor` | 2.40 x 2.60 x 0.30 | floor (opening) | 7.3k | Panel_L / Panel_R (slide), access panels, indicators, tracks |
| 7 | `OD_ENV_EmergencyBulkhead` | 2.40 x 2.60 x 0.45 | floor (opening) | 9.9k | Leaf_L / Leaf_R (hinge), ManualWheel, LockBolts, WarningLights |
| 8 | `OD_SYS_ORIONTerminal` | 0.70 x 1.55 x 0.60 | floor | 3.2k | ServicePanel, power button |
| 9 | `OD_SYS_ServerRack` | 0.60 x 2.10 x 1.00 | floor | 11.4k | 6 server sleds (slide), RearDoor |
| 10 | `OD_OBS_WindowFrame` | 15.0 x 5.10 x 0.60 | floor (glazing plane) | 6.5k | static; 3 separate glass panes |
| 11 | `OD_ENV_CeilingLight` | 0.50 x 0.14 x 2.00 (L) | ceiling (top-centre) | 2.6k | Diffuser (drop-down), StatusLights |
| 12 | `OD_ENV_WallUtilityPanel` | 1.00 x 1.20 x 0.18 | wall (rear centre) | 4.2k | PowerAccessDoor, emergency guard + button |
| 13 | `OD_ENV_VentilationModule` | 1.40 x 0.80 x 0.40 | wall (rear centre) | 4.5k | 4 louver rows, FilterHatch |
| 14 | `OD_PROP_SupplyCrate` | 1.00 x 0.70 x 0.70 | floor | 3.9k | Lid, 2 latches, 2 fold-down top handles |
| 15 | `OD_MCC_MissionControlChair` | 0.70 x 1.20 x 0.70 | floor | 4.7k | Swivel, Backrest (recline), Arm_L / Arm_R, Footrest |

The envelopes and pivots match the `SM_PROXY_*` mounting contract (`Tools/Editor/odyssey_kit_geometry.py`)
exactly, so each GLB can replace its proxy in place. Where a reference sheet quotes different numbers
(analyzer, sliding door, window, ceiling light), the contract wins, and the asset's spec notes it.

## Folder

```
GLB/        15 x OD_*.glb                        (the deliverables)
Specs/      OD_*.json + OD_*.md per asset; ValidationReport.{json,md}
Renders/    OD_*_{front34,rear34,side,top}.png, AssetLab_Wide.png, AssetLab_OperationsRow.png, ContactSheet.png
Viewer/     index.html (inspector + rotate mode), lab.html (Asset Lab), contact.html, common.js, serve.py
Source/     procedural source — editable handoff, regenerates every GLB/spec
  od_core.py   convex hard-surface primitives (chamfered boxes, prisms, rings, cylinders, tori), Surfaces, Nodes
  od_kit.py    reusable details (vents, screens, buttons, knobs, toggles, faders, strips, hazard plates, handles)
  od_gltf.py   material family, GLB writer, GLB re-loader/validator
  od_check.py  interpenetration / floating-part / envelope checks
  build_pack.py
  assets/a01_power_console.py … a15_mcc_chair.py
```

## Axes, units, pivots (and how this was verified)

* Authoring happens in **Unreal space, in centimetres**: +X is the asset front, +Y is right, +Z is up.
  An operator facing the front sees +Y on their left.
* The GLBs use **metres, Y-up glTF**: `gl = (ue.x, ue.z, ue.y) / 100`. The writer also flips the triangle
  winding. That mapping is a reflection, which is exactly the handedness change between Unreal and glTF.
  Unreal's glTF importer applies the inverse (`UE = (gl.x, gl.z, gl.y) × 100`). The asset should therefore
  arrive **unrotated and unmirrored**, with +X forward, 1 uu = 1 cm, and its pivot at the root node origin.
  In glTF terms the asset front faces +X rather than the glTF convention of +Z. That is intentional: it means
  no rotation is needed in Unreal.
* Pivot types: `floor` = bottom-centre of the envelope · `wall_base` = bottom-centre of the rear face
  (x ∈ [0, D]) · `wall` = centre of the rear face · `ceiling` = top-centre (z ∈ [−H, 0]).
* **Verified by re-loading every GLB twice.** First with the pack's own reader (`od_gltf.validate_glb`):
  bounds mapped back to UE space equal the envelope within 0.5 mm on all six sides, nodes carry translation
  only, normals are unit length, there are no NaNs and no degenerate triangles, and triangle winding agrees
  with the normals. Second with three.js `GLTFLoader` in the Asset Lab: all 15 load and report the contract
  sizes.
* **Not yet verified in the Unreal editor.** After import, check that the static mesh bounds read X = D,
  Y = W, Z = H. If X and Y come in swapped, the importer's axis option differs from the default mapping above.

## Hierarchy conventions

* Root node = asset name. Static shell = `Body*`. Emissive strips and LEDs live in `StatusLights` / `*_Lights`
  nodes, so EmissiveScale can drive them.
* Displays are `Screen_*` / `Display_*` / `Sign_*` nodes: physical plates on `OD_MAT_Display` whose front
  face has a 0..1 UV rectangle (u right, v down) for a render target. No UI text is modelled.
* Movable and interactive nodes have their **node origin on the hinge or slide pivot**. `extras.od_motion`
  describes the motion (`hinge` / `rotate` / `slide` / `press`, axis or direction in UE space, range,
  `opens_toward_ue`). The inspector's "Movable parts" slider plays these back.
* `SOCKET_*` empty nodes mark interaction points (`SOCKET_Interact_*`, `SOCKET_Sit*`, `SOCKET_Operator_*`) and
  mounting points (`SOCKET_Mount_*`, `SOCKET_Cable_*`). The FBX pipeline turns `SOCKET_` nodes into
  StaticMesh sockets. With glTF/Interchange they import as scene components or empties; the positions are also
  listed in each spec.
* Validation (`od_check.py`, 1 mm tolerance): no two parts interpenetrate, every part touches the assembly
  (no floating parts), and the envelope is exact. A build fails on any violation.

## Material family (PBR, factor-based; 1 UV unit = 1 m on non-display faces)

| Slot | Base (sRGB) | Metal | Rough | Emissive |
|---|---|---|---|---|
| OD_MAT_AerospaceWhite | #D8D9D5 | 0 | 0.42 | – |
| OD_MAT_Graphite | #1C2025 | 0 | 0.58 | – |
| OD_MAT_Gunmetal | #454B52 | 0.65 | 0.45 | – |
| OD_MAT_BrushedAluminum | #92989E | 1 | 0.30 | – |
| OD_MAT_Rubber | #141618 | 0 | 0.88 | – |
| OD_MAT_Glass | #9FB7BF, α 0.22 (BLEND) | 0 | 0.04 | – |
| OD_MAT_Display | #09131C | 0 | 0.12 | faint #0E2A3A |
| OD_MAT_IonBlue_Emissive | #61BED2 | 0 | 0.30 | ×2.2 |
| OD_MAT_Amber_Emissive | #D69A35 | 0 | 0.35 | ×1.8 |
| OD_MAT_EmergencyRed_Emissive | #B84743 | 0 | 0.35 | ×1.8 |
| OD_MAT_HazardPaint *(extension)* | #D69A35 | 0 | 0.55 | – (painted hazard stripes / handles) |
| OD_MAT_Diffuser_Emissive *(extension)* | #EEF2F3 | 0 | 0.50 | ×4 (light diffuser only) |

The two extensions reuse palette hues. Painted hazard stripes must not glow, and the ceiling-light diffuser
needs a white emitter. In Unreal, replace each slot with one master-material instance and add wear, edge
masks and decals (logos, labels, UI) there.

## Import into Unreal Engine 5.8

1. Drag `GLB/*.glb` into the Content Browser (Interchange glTF), or use **Import Into Level** to keep the node
   hierarchy as actors. Leave scale at 1.0 (metres → cm happens automatically) and add no import rotation.
2. For a single static mesh with separate movable parts, keep "Combine Meshes" **off** so every node becomes
   its own mesh, positioned at its pivot. Then build a Blueprint, or use the existing
   `AOdysseyPowerConsole` / `AOdysseyLightFixture` actors, and attach the movable meshes at the node
   translations listed in the spec.
3. Collision follows each spec's recommendation: simple UCX boxes or hulls. No collision meshes are embedded.
4. Nanite: turn it on for the opaque `Body*` meshes. Glass, which is translucent, stays non-Nanite. Small
   movable or emissive parts can go either way. Every spec lists its own recommendation.
5. Generate lightmap UVs on import if you use baked lighting. The pack targets Lumen.

## Rebuild, view, inspect

```bash
python3 -I ArtSource/OdysseyAssetPack/Source/build_pack.py          # all 15 (a few seconds, pure Python, no deps)
python3 -I ArtSource/OdysseyAssetPack/Source/build_pack.py a01 a05  # selected assets
python3 -I ArtSource/OdysseyAssetPack/Viewer/serve.py               # http://127.0.0.1:8765/Viewer/
```

The inspector offers orbit/rotate, the four inspection views, a 1.80 m human reference, bounds, pivot axes,
wireframe, the movable-part slider and "Capture inspection set" (writes `Renders/`). `lab.html` shows all 15
with a 1.80 m human that belongs to the viewer only, never to an exported asset. The viewer loads three.js r160
from jsDelivr, so it needs a network connection.

## Known limits / next steps

* **FBX was not produced.** Blender and the FBX SDK are not installed on this Mac. An FBX could not be
  re-loaded or validated here, so none was shipped. Unreal imports GLB natively. If FBX is required, import
  the GLB into Blender 4.x and export FBX (Forward −Y or X, Up Z, apply unit scale). The Python sources are the
  editable, non-flattened handoff.
* There are no textures yet: the materials are factor-only PBR, with UVs in place (world-scaled planar per
  face, 0..1 on displays).
* Sliding-door leaves retract 1.0 m into wall pockets that lie outside the 2.40 m envelope; the level
  geometry has to provide those pockets.
* If these GLBs are committed, add `*.glb filter=lfs diff=lfs merge=lfs -text` to the repo `.gitattributes`
  (PNG renders already go to LFS).
