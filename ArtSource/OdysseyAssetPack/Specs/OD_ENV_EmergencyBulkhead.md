# OD_ENV_EmergencyBulkhead - Emergency Bulkhead Door

Emergency pressure bulkhead: deep white portal with hazard-striped jambs, bolted jamb covers, red beacon housings and header alarm bar on both faces, seal-status/override panels, hazard threshold; two ribbed gunmetal pressure leaves hinged on the jambs (swing out +X) with amber marker lights, ALU lock bolts throwing into jamb keepers, and an amber manual handwheel.

Reference (visual only): `07_Bulkhead_Emergency_Door.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 2.40 (Y) x H 2.60 (Z) x D 0.45 (X) |
| Pivot | floor: bottom-centre of the opening, centred in the wall (x = 0) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 9920 |
| Collision | Custom: portal as 3 boxes (jambs + header); each leaf its own box; wheel none. |
| Nanite | Nanite ON for Frame and leaves; WarningLights/wheel small separate meshes. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENV_EmergencyBulkhead` | group | 0 |  |  |
| `Frame` | static | 5960 |  | Portal, threshold, hazard jambs, hinges, keepers |
| `WarningLights_Front` | emissive | 132 |  | Red beacons + header alarm bar (pulse via EmissiveScale) |
| `OverridePanel_Front` | interactive | 12 |  | Seal status display + override buttons |
| `OverridePanel_Front_Button_1` | interactive | 44 | {"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.3]} |  |
| `OverridePanel_Front_Button_2` | interactive | 44 | {"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.3]} |  |
| `WarningLights_Back` | emissive | 132 |  | Red beacons + header alarm bar (pulse via EmissiveScale) |
| `OverridePanel_Back` | interactive | 12 |  | Seal status display + override buttons |
| `OverridePanel_Back_Button_1` | interactive | 44 | {"type": "press", "dir_ue": [1, 0, 0], "range_cm": [0, 0.3]} |  |
| `OverridePanel_Back_Button_2` | interactive | 44 | {"type": "press", "dir_ue": [1, 0, 0], "range_cm": [0, 0.3]} |  |
| `Leaf_L` | movable | 748 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [1, 0, 0], "note": "swings out toward +X (active leaf, opens first)"} | Pressure leaf (0.12 m) |
| `Leaf_L_Lights` | emissive | 352 |  |  |
| `Leaf_L_LockBolt` | interactive | 44 | {"type": "slide", "dir_ue": [0, 0, 1], "travel_cm": 4, "note": "throws up into the header keeper to lock (rest = retracted)"} |  |
| `ManualWheel` | interactive | 1208 | {"type": "rotate", "axis_ue": [1, 0, 0], "range_deg": [0, 720], "note": "two turns retract/throw both lock bolts"} |  |
| `Leaf_R` | movable | 748 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [1, 0, 0], "note": "swings out toward +X"} | Pressure leaf (0.12 m) |
| `Leaf_R_Lights` | emissive | 352 |  |  |
| `Leaf_R_LockBolt` | interactive | 44 | {"type": "slide", "dir_ue": [0, 0, 1], "travel_cm": 4, "note": "throws up into the header keeper to lock (rest = retracted)"} |  |
| `SOCKET_Interact_Wheel` | socket | 0 |  | Manual handwheel (front) |
| `SOCKET_Interact_Override_Front` | socket | 0 |  | Front override panel |
| `SOCKET_Interact_Override_Back` | socket | 0 |  | Back override panel |
| `SOCKET_Mount_Opening` | socket | 0 |  | Pivot: bottom-centre of the wall opening |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 92 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 792 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 1948 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 24 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 352 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Graphite` | 1960 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 2272 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 2480 | #D69A35 | 0.0 | 0.55 |  |

## Emissive components

- `WarningLights_Front`: OD_MAT_EmergencyRed_Emissive
- `OverridePanel_Front_Button_1`: OD_MAT_Amber_Emissive
- `OverridePanel_Front_Button_2`: OD_MAT_EmergencyRed_Emissive
- `WarningLights_Back`: OD_MAT_EmergencyRed_Emissive
- `OverridePanel_Back_Button_1`: OD_MAT_Amber_Emissive
- `OverridePanel_Back_Button_2`: OD_MAT_EmergencyRed_Emissive
- `Leaf_L_Lights`: OD_MAT_Amber_Emissive
- `Leaf_R_Lights`: OD_MAT_Amber_Emissive

## Interaction points

- **Handwheel** (`SOCKET_Interact_Wheel`): Rotate 2 turns: bolts retract, then Leaf_L swings
- **Override (front)** (`SOCKET_Interact_Override_Front`): Seal status + override/emergency buttons
- **Override (back)** (`SOCKET_Interact_Override_Back`): Same on the back face

## Mounting points

- **Wall opening** (`SOCKET_Mount_Opening`): 2.40 x 2.60 cut in a 0.32-0.45 m pressure wall

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-22.5, -120.0, 0.0] max [22.5, 120.0, 260.0]
- Expected: min (-22.5, -120.0, 0) max (22.5, 120.0, 260)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_EmergencyRed_Emissive, OD_MAT_Display, OD_MAT_Amber_Emissive
- GLB problems: none
- Assembly: 375 solids, 1 connected component(s), 0 interpenetration(s)
