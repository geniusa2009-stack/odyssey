# OD_MCC_MissionControlChair - Mission Control Chair

Operator chair: four-arm floor base with ion arm lights and an aluminium column, 360 deg swivel assembly carrying a padded seat (0.48 m), reclining backrest with bolsters and headrest, flip-up armrests with control pads (left: selector + buttons; right: mini display + buttons) and a folding footrest with rubber treads.

Reference (visual only): `15_Mission_Control_Chair.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 0.70 (Y) x H 1.20 (Z) x D 0.70 (X) |
| Pivot | floor: bottom-centre (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 4684 |
| Collision | Custom: base cylinder (r 0.35, h 0.30) + seat box + backrest box (3 UCX). Arms/footrest: none. |
| Nanite | Nanite optional (~5k tris). Keep Swivel/Backrest/Arms/Footrest as separate components for animation. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_MCC_MissionControlChair` | group | 0 |  |  |
| `Base` | static | 1016 |  | Four-arm floor base, hub, column (does not swivel) |
| `StatusLights` | emissive | 368 |  | Base arm lights and column ring |
| `Swivel` | movable | 0 | {"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-180, 180]} | Everything above the column swivels 360 deg |
| `Seat` | static | 584 |  | Seat frame, side covers, cushion |
| `Seat_Lights` | emissive | 88 |  |  |
| `Backrest` | movable | 308 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 22], "opens_toward_ue": [-1, 0, 0], "note": "recline (rest pose = 8 deg)"} |  |
| `Backrest_Lights` | emissive | 176 |  |  |
| `Arm_L` | movable | 220 | {"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 80, "opens_toward_ue": [0, 0, 1], "note": "armrest flips up for ingress"} |  |
| `Arm_L_Controls` | interactive | 964 |  | Arm control pad (buttons/knob/display) |
| `Arm_R` | movable | 220 | {"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 80, "opens_toward_ue": [0, 0, 1], "note": "armrest flips up for ingress"} |  |
| `Arm_R_Controls` | interactive | 332 |  | Arm control pad (buttons/knob/display) |
| `Arm_R_Display` | display | 12 |  |  |
| `Footrest` | movable | 396 | {"type": "hinge", "axis_ue": [0, 1, 0], "range_deg": [0, 75], "opens_toward_ue": [0, 0, 1], "note": "folds up under the seat front"} |  |
| `SOCKET_Sit` | socket | 0 |  | Seated pelvis anchor (seat top) |
| `SOCKET_Interact_ArmL` | socket | 0 |  | Left arm control pad |
| `SOCKET_Interact_ArmR` | socket | 0 |  | Right arm display pad |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 176 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 88 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 684 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 12 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_Graphite` | 1048 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 984 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_IonBlue_Emissive` | 1076 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 616 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Seat_Lights`: OD_MAT_IonBlue_Emissive
- `Backrest_Lights`: OD_MAT_IonBlue_Emissive
- `Arm_L`: OD_MAT_IonBlue_Emissive
- `Arm_L_Controls`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Arm_R`: OD_MAT_IonBlue_Emissive
- `Arm_R_Controls`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Footrest`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Sit** (`SOCKET_Sit`): Seat anchor; Swivel yaw follows the operator
- **Left arm pad** (`SOCKET_Interact_ArmL`): Selector and buttons
- **Right arm pad** (`SOCKET_Interact_ArmR`): Mini display and buttons

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing on four arms

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-35.0, -35.0, 0.0] max [35.0, 35.0, 120.0]
- Expected: min (-35.0, -35.0, 0) max (35.0, 35.0, 120)
- Material slots: OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_Rubber, OD_MAT_IonBlue_Emissive, OD_MAT_AerospaceWhite, OD_MAT_Amber_Emissive, OD_MAT_Display
- GLB problems: none
- Assembly: 84 solids, 1 connected component(s), 0 interpenetration(s)
