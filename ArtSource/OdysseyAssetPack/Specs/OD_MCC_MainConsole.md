# OD_MCC_MainConsole - Mission Control Main Console

Three-segment mission control console: straight 1.60 m centre segment with e-stop, three mode levers and button bank, plus two 1.36 m wings angled 32.8 deg toward the operators, joined by wedge pillars. Each segment has a vented front with ion strips, a sloped seated-height desk with control modules (wings: desk display + buttons), and a reclined hood with two displays and a header strip; header block on the centre hood.

Reference (visual only): `05_Mission_Control_Main_Console.png, 05B_Mission_Control_Reference_Sheet.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 4.80 (Y) x H 1.30 (Z) x D 1.60 (X) |
| Pivot | floor: bottom-centre of the envelope (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 19516 |
| Collision | Custom: per segment one box for the lower body+desk and one for the hood (6 UCX) + 2 wedge hulls. |
| Nanite | Body segments Nanite ON; displays and controls separate (render targets / interaction). |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_MCC_MainConsole` | group | 0 |  |  |
| `StatusLights` | emissive | 2300 |  | Ion strips / LEDs of all segments |
| `Controls` | group | 0 |  | Desk controls of all segments |
| `Control_Buttons_Centre` | interactive | 792 | {"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]} | Momentary button caps |
| `Control_Knob_Centre` | interactive | 388 | {"type": "rotate", "axis_ue": [0.2265, 0.0, 0.974], "range_deg": [-135, 135]} |  |
| `Control_ModeLever_01_Centre` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_ModeLever_02_Centre` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_ModeLever_03_Centre` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_EStop_Centre` | interactive | 312 | {"type": "slide", "dir_ue": [-0.2265, -0.0, -0.974], "range_cm": [0, 0.8]} |  |
| `Control_Buttons_WingL` | interactive | 1100 | {"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]} | Momentary button caps |
| `Control_Knob_WingL` | interactive | 388 | {"type": "rotate", "axis_ue": [0.1904, -0.1226, 0.974], "range_deg": [-135, 135]} |  |
| `Control_Buttons_WingR` | interactive | 1100 | {"type": "press", "dir_ue": [0, 0, -1], "range_cm": [0, 0.3]} | Momentary button caps |
| `Control_Knob_WingR` | interactive | 388 | {"type": "rotate", "axis_ue": [0.1904, 0.1226, 0.974], "range_deg": [-135, 135]} |  |
| `Body_Centre` | static | 4796 |  | Centre segment shell, desk, hood, modules |
| `Display_A_Centre` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Display_B_Centre` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Body_WingL` | static | 3756 |  | WingL segment shell, desk, hood, modules |
| `DeskDisplay_WingL` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Display_A_WingL` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Display_B_WingL` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Joint_WingL` | static | 48 |  | Wedge joint between centre and wing |
| `Body_WingR` | static | 3756 |  | WingR segment shell, desk, hood, modules |
| `DeskDisplay_WingR` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Display_A_WingR` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Display_B_WingR` | display | 12 |  | 0..1 UV on OD_MAT_Display |
| `Joint_WingR` | static | 48 |  | Wedge joint between centre and wing |
| `HeaderBlock` | static | 44 |  | ODYSSEY Mission Control header block |
| `SOCKET_Operator_Centre` | socket | 0 |  | Centre operator position (chair) |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 592 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 836 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 1284 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 96 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 356 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Graphite` | 6192 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 5596 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 116 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 4448 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Control_Buttons_Centre`: OD_MAT_Amber_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_IonBlue_Emissive
- `Control_ModeLever_01_Centre`: OD_MAT_IonBlue_Emissive
- `Control_ModeLever_02_Centre`: OD_MAT_IonBlue_Emissive
- `Control_ModeLever_03_Centre`: OD_MAT_IonBlue_Emissive
- `Control_EStop_Centre`: OD_MAT_EmergencyRed_Emissive
- `Control_Buttons_WingL`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Control_Buttons_WingR`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive

## Interaction points

- **Displays** (`Display_A_Centre`): Six hood displays + two desk displays (render targets)
- **Emergency stop** (`Control_EStop_Centre`): Centre desk
- **Mode levers** (`Control_ModeLever_01_Centre`): Normal / Test / Override
- **Operator** (`SOCKET_Operator_Centre`): Chair positions in front of each segment

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing arc; the 8.6 m room-scale ring of the 05B sheet is built from this unit plus wall displays

## Notes

- Solved wing length 135.83 cm and angle 32.782 deg so the arc fills 4.80 x 1.60 m exactly.
- 05B sheet shows the full 8.6 x 3.2 m command ring; the contract unit is this 4.80 x 1.30 x 1.60 m console.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-80.0, -240.0, 0.0] max [80.0, 240.0, 130.0]
- Expected: min (-80.0, -240.0, 0) max (80.0, 240.0, 130)
- Material slots: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_AerospaceWhite, OD_MAT_HazardPaint, OD_MAT_Display
- GLB problems: none
- Assembly: 497 solids, 1 connected component(s), 0 interpenetration(s)
