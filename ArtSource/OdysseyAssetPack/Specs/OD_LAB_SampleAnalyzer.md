# OD_LAB_SampleAnalyzer - Laboratory Sample Analyzer

Automated sample analyzer: cabinet with vented side pods on corner feet, 0.98 m worktop with mode buttons, selector knob, cartridge tray tunnel and mushroom e-stop; glazed sample chamber with sliding glass door, 10-vial sample rack and an analysis head with ion ring; two toed-in analysis displays; top housing with status strip; rear service column and hinged maintenance panel.

Reference (visual only): `04_Laboratory_Sample_Analyzer_Ref.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.60 (Y) x H 1.70 (Z) x D 0.90 (X) |
| Pivot | floor: bottom-centre (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 10148 |
| Collision | Custom: cabinet box + worktop box + chamber box + top housing box (4 UCX). |
| Nanite | Body Nanite ON; glass (chamber, door, vials) translucent - non-Nanite. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_LAB_SampleAnalyzer` | group | 0 |  |  |
| `Body` | static | 5460 |  | Base, cabinet, pods, worktop, top housing, rear column |
| `StatusLights` | emissive | 840 |  | Status strips and LEDs |
| `MaintenancePanel` | movable | 780 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [-1, 0, 0]} | Rear maintenance access panel |
| `Controls` | group | 0 |  | Worktop controls |
| `Control_Buttons` | interactive | 484 | {"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]} | Load off / Load nominal / Diagnostic / mode buttons |
| `Control_Knob` | interactive | 388 | {"type": "rotate", "axis_ue": [0, 0, 1], "range_deg": [-135, 135]} |  |
| `Control_EStop` | interactive | 312 | {"type": "slide", "dir_ue": [0, 0, -1], "range_cm": [0, 0.8], "note": "emergency stop"} |  |
| `CartridgeTray` | movable | 220 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 14, "note": "insert / eject"} | Sample cartridge slot tray |
| `SampleChamber` | static | 444 |  | Chamber frame, side glazing, rear wall, analysis head |
| `SampleChamber_Lights` | emissive | 192 |  |  |
| `SampleArea` | interactive | 936 |  | Sample rack with 10 vials (pickable sample positions) |
| `ChamberDoor` | movable | 68 | {"type": "slide", "dir_ue": [0, 0, 1], "travel_cm": 40, "note": "glass door slides up behind the top housing"} | Sliding glass chamber door |
| `Display_L` | display | 12 |  | Analysis display (0..1 UV on OD_MAT_Display) |
| `Display_R` | display | 12 |  | Analysis display (0..1 UV on OD_MAT_Display) |
| `SOCKET_Interact_Chamber` | socket | 0 |  | Chamber door handle / sample access |
| `SOCKET_Interact_Cartridge` | socket | 0 |  | Cartridge tray pull |
| `SOCKET_Interact_EStop` | socket | 0 |  | Emergency stop |
| `SOCKET_Interact_Controls` | socket | 0 |  | Mode buttons (load off / nominal / diagnostic) |
| `SOCKET_Interact_Display_L` | socket | 0 |  | Left display |
| `SOCKET_Interact_Display_R` | socket | 0 |  | Right display |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 352 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 132 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 1556 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 24 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 400 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Glass` | 476 | #9FB7BF | 0.0 | 0.04 |  |
| `OD_MAT_Graphite` | 1856 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 3636 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 232 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 1308 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 176 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Control_Buttons`: OD_MAT_Amber_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_IonBlue_Emissive
- `Control_EStop`: OD_MAT_EmergencyRed_Emissive
- `SampleChamber_Lights`: OD_MAT_IonBlue_Emissive
- `SampleArea`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Sample chamber** (`SOCKET_Interact_Chamber`): Door slides up 0.40 m
- **Cartridge tray** (`SOCKET_Interact_Cartridge`): Slides out 0.14 m
- **Emergency stop** (`SOCKET_Interact_EStop`): Immediate isolation
- **Mode buttons** (`SOCKET_Interact_Controls`): Load off / nominal / diagnostic
- **Displays** (`SOCKET_Interact_Display_L`): Analysis UI (L and R)

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing; 0.30 m rear clearance for the maintenance panel

## Notes

- Reference sheet quotes 2.00 x 1.58 x 0.95 m; this follows the prototype contract 1.60 x 1.70 x 0.90 m.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-45.0, -80.0, 0.0] max [45.0, 80.0, 170.0]
- Expected: min (-45.0, -80.0, 0) max (45.0, 80.0, 170)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Rubber, OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_Glass, OD_MAT_Display
- GLB problems: none
- Assembly: 269 solids, 1 connected component(s), 0 interpenetration(s)
