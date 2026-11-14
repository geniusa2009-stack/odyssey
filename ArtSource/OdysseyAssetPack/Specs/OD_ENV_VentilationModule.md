# OD_ENV_VentilationModule - Ventilation Module

Wall ventilation unit: chamfered white housing with a deep louver bay (four adjustable rows across three bays split by gunmetal dividers), recessed filter plenum, gunmetal bay bezel, airflow status strip, side slot vents with graphite corner caps and a drop-down filter hatch.

Reference (visual only): `13_Ventilation_Module.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.40 (Y) x H 0.80 (Z) x D 0.40 (X) |
| Pivot | wall: centre of the rear face (flush to wall) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 4452 |
| Collision | None (wall detail) or one box 0.40 x 1.40 x 0.80. |
| Nanite | Nanite ON for Body; louver rows and hatch as small separate meshes. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENV_VentilationModule` | group | 0 |  |  |
| `Body` | static | 3080 |  | Housing, plenum, bezel, dividers, vents |
| `StatusLights` | emissive | 220 |  | Airflow status strip |
| `Louvers` | group | 0 |  | Adjustable louver rows (rotate about Y) |
| `Louver_Row_01` | interactive | 132 | {"type": "rotate", "axis_ue": [0, 1, 0], "range_deg": [-35, 35]} |  |
| `Louver_Row_02` | interactive | 132 | {"type": "rotate", "axis_ue": [0, 1, 0], "range_deg": [-35, 35]} |  |
| `Louver_Row_03` | interactive | 132 | {"type": "rotate", "axis_ue": [0, 1, 0], "range_deg": [-35, 35]} |  |
| `Louver_Row_04` | interactive | 132 | {"type": "rotate", "axis_ue": [0, 1, 0], "range_deg": [-35, 35]} |  |
| `FilterHatch` | movable | 624 | {"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 90, "opens_toward_ue": [1, 0, 0], "note": "drops down on its bottom edge for filter change"} |  |
| `SOCKET_Interact_FilterHatch` | socket | 0 |  | Filter hatch pull |
| `SOCKET_Interact_Louvers` | socket | 0 |  | Louver adjust / airflow look-at |
| `SOCKET_FX_Airflow` | socket | 0 |  | Air outlet: particle/airflow FX origin, +X |
| `SOCKET_Mount_Wall` | socket | 0 |  | Pivot: centre of rear face, flush to wall |
| `SOCKET_Mount_Anchor_1` | socket | 0 |  | Wall anchor through wall plate |
| `SOCKET_Mount_Anchor_2` | socket | 0 |  | Wall anchor through wall plate |
| `SOCKET_Mount_Anchor_3` | socket | 0 |  | Wall anchor through wall plate |
| `SOCKET_Mount_Anchor_4` | socket | 0 |  | Wall anchor through wall plate |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 172 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_BrushedAluminum` | 932 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Graphite` | 1528 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 1564 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 36 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 220 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Filter hatch** (`SOCKET_Interact_FilterHatch`): Drops 90 deg
- **Louvers** (`SOCKET_Interact_Louvers`): Rows rotate +-35 deg

## Mounting points

- **Wall** (`SOCKET_Mount_Wall`): Flush to wall; four anchors

## Validation (re-loaded GLB)

- Bounds (UE cm): min [0.0, -70.0, -40.0] max [40.0, 70.0, 40.0]
- Expected: min (0, -70.0, -40.0) max (40, 70.0, 40.0)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_IonBlue_Emissive
- GLB problems: none
- Assembly: 187 solids, 1 connected component(s), 0 interpenetration(s)
