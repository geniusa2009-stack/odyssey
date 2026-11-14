# OD_ENG_PowerBusB - Power Bus B Cabinet

Wall-standing power distribution cabinet for Bus B. Stacked front modules: exhaust header, status display with LED column, three main breakers with throw levers and a guarded toggle sub-panel, an eight-way MCB strip on a DIN rail, and a hinged lower cable compartment door. Corner feet on a recessed plinth with intake grille; vertical grab handles; top lifting bars and cable glands.

Reference (visual only): `02_Power_Bus_B_Cabinet.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.20 (Y) x H 2.20 (Z) x D 0.60 (X) |
| Pivot | wall_base: bottom-centre of the rear face (rear flush to wall) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 9160 |
| Collision | Simple: one box 0.60 x 1.20 x 2.20 (UCX). AccessDoor: own box when opened. |
| Nanite | Body: Nanite ON. Levers/toggles/door/display: separate small meshes, Nanite optional. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENG_PowerBusB` | group | 0 |  |  |
| `Body` | static | 6992 |  | Cabinet shell, plinth, module panels, breaker housings |
| `StatusLights` | emissive | 676 |  | Header strip, plinth lights, LEDs (EmissiveScale) |
| `Screen_Status` | display | 12 |  | Bus B load display (0..1 UV on OD_MAT_Display) |
| `Breaker_Main_01` | interactive | 88 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-35, 35], "note": "lever throws up (ON) / down (OFF) about Y"} |  |
| `Breaker_Main_02` | interactive | 88 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-35, 35], "note": "lever throws up (ON) / down (OFF) about Y"} |  |
| `Breaker_Main_03` | interactive | 88 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-35, 35], "note": "lever throws up (ON) / down (OFF) about Y"} |  |
| `Toggle_01` | interactive | 60 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-40, 40]} |  |
| `Toggle_02` | interactive | 60 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-40, 40]} |  |
| `MCB_Strip` | group | 0 |  | Eight miniature breakers; each toggle is its own node |
| `MCB_Toggle_01` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_02` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_03` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_04` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_05` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_06` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_07` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `MCB_Toggle_08` | interactive | 44 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [-30, 30]} |  |
| `AccessDoor` | movable | 744 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 105, "opens_toward_ue": [1, 0, 0]} | Lower cable compartment door, hinge on the +Y edge |
| `SOCKET_Interact_Breakers` | socket | 0 |  | Main breaker bank (3 levers) |
| `SOCKET_Interact_Screen` | socket | 0 |  | Status display |
| `SOCKET_Interact_MCB` | socket | 0 |  | MCB strip |
| `SOCKET_Interact_AccessDoor` | socket | 0 |  | Door pull |
| `SOCKET_Mount_Wall` | socket | 0 |  | Pivot: rear face bottom-centre, flush to wall |
| `SOCKET_Mount_WallAnchor_L` | socket | 0 |  | Upper wall anchor (M12) through rear panel |
| `SOCKET_Mount_WallAnchor_R` | socket | 0 |  | Upper wall anchor (M12) through rear panel |
| `SOCKET_Cable_Top` | socket | 0 |  | Top cable gland plate |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 528 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_BrushedAluminum` | 2624 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 12 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 132 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Graphite` | 1512 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 2864 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 264 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 676 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 548 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Breaker_Main_01`: OD_MAT_EmergencyRed_Emissive
- `Breaker_Main_02`: OD_MAT_EmergencyRed_Emissive
- `Breaker_Main_03`: OD_MAT_EmergencyRed_Emissive

## Interaction points

- **Main breakers** (`SOCKET_Interact_Breakers`): Throw levers ON/OFF (hinge about Y)
- **Status display** (`SOCKET_Interact_Screen`): Bus load UI
- **MCB strip** (`SOCKET_Interact_MCB`): 8 toggles
- **Access door** (`SOCKET_Interact_AccessDoor`): Opens 105 deg

## Mounting points

- **Wall** (`SOCKET_Mount_Wall`): Rear flush to wall; floor standing on 4 feet
- **Wall anchors** (`SOCKET_Mount_WallAnchor_L`): Two upper anchors (L/R)
- **Cable entry** (`SOCKET_Cable_Top`): Top gland plate

## Validation (re-loaded GLB)

- Bounds (UE cm): min [0.0, -60.0, 0.0] max [60.0, 60.0, 220.0]
- Expected: min (0, -60.0, 0) max (60, 60.0, 220)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Rubber, OD_MAT_IonBlue_Emissive, OD_MAT_Display, OD_MAT_EmergencyRed_Emissive
- GLB problems: none
- Assembly: 246 solids, 1 connected component(s), 0 interpenetration(s)
