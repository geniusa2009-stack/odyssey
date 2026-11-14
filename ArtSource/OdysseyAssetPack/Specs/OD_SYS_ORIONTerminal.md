# OD_SYS_ORIONTerminal - ORION Physical Terminal

Free-standing ORION kiosk: weighted graphite base with aluminium trim, graphite tower leaning back 7 deg, aluminium fascia carrying a portrait touch display and camera pod, speaker / mic / power band, ion status bar, hinged white service panel, aluminium side accents and a vented rear hatch with cable gland.

Reference (visual only): `08B_ORION_Physical_Terminal.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 0.70 (Y) x H 1.55 (Z) x D 0.60 (X) |
| Pivot | floor: bottom-centre of the base (floor contact) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 3220 |
| Collision | Simple: base box + tower convex hull (2 UCX). |
| Nanite | Nanite ON for Body; display/button/panel separate. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_SYS_ORIONTerminal` | group | 0 |  |  |
| `Body` | static | 2532 |  | Base, tower, fascia, bands, rear hatch |
| `StatusLights` | emissive | 176 |  | Front ion status bar |
| `ServicePanel` | movable | 328 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 100, "opens_toward_ue": [1, 0, 0]} | Lower service panel, hinge on the -Y edge |
| `Control_PowerButton` | interactive | 172 | {"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.3]} |  |
| `Screen_Main` | display | 12 |  | Portrait touch display (0..1 UV on OD_MAT_Display) |
| `SOCKET_Interact_Screen` | socket | 0 |  | Touch display centre (look-at / UI widget anchor) |
| `SOCKET_Interact_Power` | socket | 0 |  | Power button |
| `SOCKET_User_Stand` | socket | 0 |  | User floor position |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot (anchor bolts through base) |
| `SOCKET_Cable_Rear` | socket | 0 |  | Rear cable gland |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 44 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_BrushedAluminum` | 1104 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 12 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_Glass` | 60 | #9FB7BF | 0.0 | 0.04 |  |
| `OD_MAT_Graphite` | 556 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 972 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_IonBlue_Emissive` | 304 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 168 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Control_PowerButton`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Touch display** (`SOCKET_Interact_Screen`): ORION UI render target
- **Power** (`SOCKET_Interact_Power`): Press
- **User position** (`SOCKET_User_Stand`): Stand here

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing / bolted
- **Cable** (`SOCKET_Cable_Rear`): Rear

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-30.0, -35.0, 0.0] max [30.0, 35.0, 155.0]
- Expected: min (-30.0, -35.0, 0) max (30.0, 35.0, 155)
- Material slots: OD_MAT_BrushedAluminum, OD_MAT_Glass, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_Rubber, OD_MAT_IonBlue_Emissive, OD_MAT_AerospaceWhite, OD_MAT_Display
- GLB problems: none
- Assembly: 82 solids, 1 connected component(s), 0 interpenetration(s)
