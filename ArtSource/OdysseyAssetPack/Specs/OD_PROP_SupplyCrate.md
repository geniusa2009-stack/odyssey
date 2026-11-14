# OD_PROP_SupplyCrate - Supply Crate

Two-piece hard-shell supply crate: lower shell on fork skids, hinged lid with raised panel, graphite corner bumpers and wrap straps, two over-centre latches spanning the seam, fold-down top handles and side carry handles with intake vents.

Reference (visual only): `14_Supply_Cargo_Crate.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.00 (Y) x H 0.70 (Z) x D 0.70 (X) |
| Pivot | floor: bottom-centre (floor contact under the skids) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 3936 |
| Collision | Simple: one box 0.70 x 1.00 x 0.62 (handles excluded). Physics-simulated prop friendly. |
| Nanite | Nanite optional (6-7k tris). For physics props keep a simple UCX box. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_PROP_SupplyCrate` | group | 0 |  |  |
| `Body` | static | 2476 |  | Lower shell, skids, corner bumpers, straps, side handles |
| `StatusLights` | emissive | 220 |  | Front ion status strips |
| `Lid` | movable | 872 | {"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 100, "opens_toward_ue": [0, 0, 1]} | Lid hinges on the rear top edge |
| `Handle_Top_R` | movable | 132 | {"type": "hinge", "axis_ue": [1, 0, 0], "range_deg": [0, 85], "note": "folds flat"} |  |
| `Handle_Top_L` | movable | 132 | {"type": "hinge", "axis_ue": [1, 0, 0], "range_deg": [0, 85], "note": "folds flat"} |  |
| `Latch_L` | interactive | 52 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 70], "note": "flips down to release"} |  |
| `Latch_R` | interactive | 52 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 70], "note": "flips down to release"} |  |
| `SOCKET_Interact_Lid` | socket | 0 |  | Open/close lid (latches first) |
| `SOCKET_Interact_Latch_L` | socket | 0 |  | Latch L |
| `SOCKET_Interact_Latch_R` | socket | 0 |  | Latch R |
| `SOCKET_Carry_L` | socket | 0 |  | Side carry handle (+Y) |
| `SOCKET_Carry_R` | socket | 0 |  | Side carry handle (-Y) |
| `SOCKET_Stack_Top` | socket | 0 |  | Stacking point (top handles folded: 0.62 m) |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 176 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_BrushedAluminum` | 1160 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Graphite` | 1008 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 1312 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 16 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 264 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Lid`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Lid** (`SOCKET_Interact_Lid`): Hinge 100 deg after both latches release
- **Latches** (`SOCKET_Interact_Latch_L`): Flip down 70 deg
- **Carry** (`SOCKET_Carry_L`): Two-hand carry / drag

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Rests on skids
- **Stack** (`SOCKET_Stack_Top`): Stackable

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-35.0, -50.0, 0.0] max [35.0, 50.0, 70.0]
- Expected: min (-35.0, -50.0, 0) max (35.0, 50.0, 70)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_IonBlue_Emissive, OD_MAT_HazardPaint
- GLB problems: none
- Assembly: 93 solids, 1 connected component(s), 0 interpenetration(s)
