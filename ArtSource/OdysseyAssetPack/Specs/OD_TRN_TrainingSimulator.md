# OD_TRN_TrainingSimulator - Training Simulator

Walk-on crew training simulator: 0.14 m chamfered platform with floor gratings, ion edge lights and a hazard step edge; rear wall unit with two white columns (energy-cell windows, vents, access panels), header beam with sign display and down-lights, a 2.1 x 1.1 m main simulation screen, an instructor desk (desk display, knob, three faders, button banks, e-stop) and a swivelling trainee seat with arm consoles facing the screen.

Reference (visual only): `03_Training_Simulator.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 3.20 (Y) x H 2.80 (Z) x D 3.80 (X) |
| Pivot | floor: bottom-centre of the plinth (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 13904 |
| Collision | Custom: platform box (walkable, 0.14 m step), rear wall unit box, desk box, seat pedestal cylinder + seat box (5 UCX). |
| Nanite | Body Nanite ON (large, many bevels). Screen/sign/seat/controls separate. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_TRN_TrainingSimulator` | group | 0 |  |  |
| `Body` | static | 8348 |  | Platform, rear wall unit, columns, header, desk |
| `StatusLights` | emissive | 1756 |  | Platform edge, column cores, header accents |
| `Sign_Header` | display | 12 |  | ODYSSEY Training Simulator sign (0..1 UV) |
| `Screen_Main` | display | 12 |  | Main simulation screen (0..1 UV on OD_MAT_Display) |
| `Controls` | group | 0 |  | Instructor / trainee desk controls |
| `Control_Knob` | interactive | 388 | {"type": "rotate", "axis_ue": [0.1863, 0.0, 0.9825], "range_deg": [-135, 135]} |  |
| `Control_Fader_01` | interactive | 68 | {"type": "slide", "dir_ue": [-0.9825, 0.0, 0.1863], "range_cm": [-10.8, 10.8]} |  |
| `Control_Fader_02` | interactive | 68 | {"type": "slide", "dir_ue": [-0.9825, 0.0, 0.1863], "range_cm": [-10.8, 10.8]} |  |
| `Control_Fader_03` | interactive | 68 | {"type": "slide", "dir_ue": [-0.9825, 0.0, 0.1863], "range_cm": [-10.8, 10.8]} |  |
| `Control_EStop` | interactive | 312 | {"type": "slide", "dir_ue": [-0.1863, -0.0, -0.9825], "range_cm": [0, 0.8]} |  |
| `Control_Buttons` | interactive | 748 | {"type": "press", "dir_ue": [-0.1863, -0.0, -0.9825], "range_cm": [0, 0.3]} |  |
| `Screen_Desk` | display | 12 |  | Desk scenario display |
| `SimSeat_Base` | static | 440 |  | Seat pedestal on the platform |
| `SimSeat` | movable | 1320 | {"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-120, 120]} | Trainee seat (swivel); arm consoles carry the trainee controls |
| `SimSeat_Lights` | emissive | 352 |  |  |
| `SOCKET_Interact_Desk` | socket | 0 |  | Desk controls (instructor) |
| `SOCKET_Interact_Screen` | socket | 0 |  | Main simulation screen centre |
| `SOCKET_Sit_Trainee` | socket | 0 |  | Trainee seat anchor (faces -X) |
| `SOCKET_Board` | socket | 0 |  | Step-on point at the platform front edge |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot (plinth bottom-centre) |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 608 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 132 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 2176 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 36 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 312 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Graphite` | 3116 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 4156 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 388 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 2848 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 132 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Control_Fader_01`: OD_MAT_IonBlue_Emissive
- `Control_Fader_02`: OD_MAT_IonBlue_Emissive
- `Control_Fader_03`: OD_MAT_IonBlue_Emissive
- `Control_EStop`: OD_MAT_EmergencyRed_Emissive
- `Control_Buttons`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `SimSeat`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `SimSeat_Lights`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Desk** (`SOCKET_Interact_Desk`): Scenario controls
- **Main screen** (`SOCKET_Interact_Screen`): Simulation render target
- **Trainee seat** (`SOCKET_Sit_Trainee`): Sit; seat swivels +-120 deg
- **Boarding** (`SOCKET_Board`): Step onto platform

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing; needs 2.9 m ceiling clearance

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-190.0, -160.0, 0.0] max [190.0, 160.0, 280.0]
- Expected: min (-190.0, -160.0, 0) max (190.0, 160.0, 280)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_IonBlue_Emissive, OD_MAT_Display, OD_MAT_EmergencyRed_Emissive, OD_MAT_Amber_Emissive, OD_MAT_Rubber
- GLB problems: none
- Assembly: 375 solids, 1 connected component(s), 0 interpenetration(s)
