# OD_ENG_PowerConsole - Power Console (Engineering)

Free-standing engineering power distribution console. Seated-height sloped control desk (front edge 0.74 m) with five control modules: selector knob bank, interlock buttons, three bus-load faders, dual rotary selectors and a mushroom emergency stop on a hazard plate. Reclined main schematic display flanked by toed-in status displays. Side equipment pods with recessed intake vents; hinged front service door; bolted rear hatch with cable glands and a rear exhaust grille.

Reference (visual only): `01_Power_Console.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.80 (Y) x H 1.25 (Z) x D 0.90 (X) |
| Pivot | floor: bottom-centre of the envelope (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 16172 |
| Collision | Custom: 4 convex hulls (UCX) - plinth+lower body box (0.90 x 1.80 x 0.62), desk wedge, display housing prism, rear feet. Controls: no collision; use per-control trigger boxes for interaction traces. ServicePanel: own simple box when opened. |
| Nanite | Body: Nanite ON (dense bevels/screws, static). Screens, controls, ServicePanel, StatusLights: Nanite optional (low poly, movable/emissive) - keep them as separate static mesh components. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENG_PowerConsole` | group | 0 |  |  |
| `Body` | static | 11092 |  | Static shell, desk, housing, bezels, vents, control bases |
| `StatusLights` | emissive | 1640 |  | Ion/amber/red status strips and LEDs (drive EmissiveScale) |
| `ServicePanel` | movable | 532 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 95, "opens_toward_ue": [1, 0, 0], "note": "free edge (+Y) swings out toward +X"} | Front service door, hinge on the -Y edge |
| `Controls` | group | 0 |  | Interactive desk controls; caps/levers are separate nodes |
| `Control_Knob_01` | interactive | 388 | {"type": "rotate", "axis_ue": [0.2265, 0.0, 0.974], "range_deg": [-135, 135]} |  |
| `Control_Toggle_01` | interactive | 60 | {"type": "hinge", "axis_ue": [0.0, -1.0, 0.0], "range_deg": [-40, 40]} |  |
| `Control_Toggle_02` | interactive | 60 | {"type": "hinge", "axis_ue": [0.0, -1.0, 0.0], "range_deg": [-40, 40]} |  |
| `Control_Toggle_03` | interactive | 60 | {"type": "hinge", "axis_ue": [0.0, -1.0, 0.0], "range_deg": [-40, 40]} |  |
| `Control_Fader_01` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_Fader_02` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_Fader_03` | interactive | 68 | {"type": "slide", "dir_ue": [-0.974, 0.0, 0.2265], "range_cm": [-8.8, 8.8]} |  |
| `Control_Knob_02` | interactive | 388 | {"type": "rotate", "axis_ue": [0.2265, 0.0, 0.974], "range_deg": [-135, 135]} |  |
| `Control_Knob_03` | interactive | 388 | {"type": "rotate", "axis_ue": [0.2265, 0.0, 0.974], "range_deg": [-135, 135]} |  |
| `Control_EStop` | interactive | 312 | {"type": "slide", "dir_ue": [-0.2265, -0.0, -0.974], "range_cm": [0, 0.8], "note": "press to latch, twist to release"} |  |
| `Control_Buttons` | interactive | 1012 | {"type": "press", "dir_ue": [-0.2265, -0.0, -0.974], "range_cm": [0, 0.3]} | All momentary button caps (one node; press = translate -n 0.3 cm per cap in code/BP) |
| `Screen_Main` | display | 12 |  | Main bus schematic display (0..1 UV on OD_MAT_Display) |
| `Screen_Left` | display | 12 |  | Side status display (0..1 UV on OD_MAT_Display) |
| `Screen_Right` | display | 12 |  | Side status display (0..1 UV on OD_MAT_Display) |
| `SOCKET_Interact_MainScreen` | socket | 0 |  | Look-at / focus point of the main display |
| `SOCKET_Interact_Desk` | socket | 0 |  | Hand/IK target over the fader bank |
| `SOCKET_Interact_EStop` | socket | 0 |  | E-stop cap top |
| `SOCKET_Interact_ServicePanel` | socket | 0 |  | Service door pull |
| `SOCKET_Operator_Stand` | socket | 0 |  | Operator floor position (seated chair or standing) |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor mount = pivot |
| `SOCKET_Cable_Rear` | socket | 0 |  | Rear cable gland plate (power feed in) |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 632 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 176 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 3428 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 36 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 488 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Graphite` | 2928 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 5344 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 132 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 2336 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 672 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Control_Fader_01`: OD_MAT_IonBlue_Emissive
- `Control_Fader_02`: OD_MAT_IonBlue_Emissive
- `Control_Fader_03`: OD_MAT_IonBlue_Emissive
- `Control_EStop`: OD_MAT_EmergencyRed_Emissive
- `Control_Buttons`: OD_MAT_Amber_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_IonBlue_Emissive

## Interaction points

- **Main display** (`SOCKET_Interact_MainScreen`): Bus schematic UI; render target on OD_MAT_Display
- **Desk controls** (`SOCKET_Interact_Desk`): Knobs rotate, faders slide, toggles flip, buttons press
- **Emergency stop** (`SOCKET_Interact_EStop`): Press to latch; drives emergency state
- **Service door** (`SOCKET_Interact_ServicePanel`): Hinged maintenance access

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing; pivot on floor, 4 feet with rubber pads
- **Cable feed** (`SOCKET_Cable_Rear`): Rear gland plate; leave >= 0.30 m rear clearance

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-45.0, -90.0, 0.0] max [45.0, 90.0, 125.0]
- Expected: min (-45.0, -90.0, 0) max (45.0, 90.0, 125)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Rubber, OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_Display
- GLB problems: none
- Assembly: 368 solids, 1 connected component(s), 0 interpenetration(s)
