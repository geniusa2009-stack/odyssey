# OD_SYS_ServerRack - Server Equipment Rack

ORION Systems server rack: graphite cabinet framed by white corner pillars with ion light strips, six pull-out server sleds with honeycomb faces, LEDs and amber handles, a central status display module with ID reader, a lower intake grille, amber side cable conduits, corner feet on a recessed base with hazard plate and a hinged rear door.

Reference (visual only): `09_Server_Equipment_Rack.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 0.60 (Y) x H 2.10 (Z) x D 1.00 (X) |
| Pivot | floor: bottom-centre (floor contact under the feet) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 11360 |
| Collision | Simple: one box 1.00 x 0.60 x 2.10 (UCX). Sleds: own box when pulled out. |
| Nanite | Nanite ON for Body; sleds/door/display separate. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_SYS_ServerRack` | group | 0 |  |  |
| `Body` | static | 4476 |  | Frame, pillars, panels, base, modules |
| `StatusLights` | emissive | 396 |  | Pillar strips, header and base lights |
| `Sled_01` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Sled_02` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Sled_03` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Sled_04` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Sled_05` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Sled_06` | movable | 860 | {"type": "slide", "dir_ue": [1, 0, 0], "travel_cm": 60, "note": "pulls out on rails"} | Server sled (1 of 6) |
| `Screen_Status` | display | 12 |  | Rack status display (0..1 UV) |
| `RearDoor` | movable | 1316 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 110, "opens_toward_ue": [-1, 0, 0]} | Rear service door, hinge on the +Y edge |
| `SOCKET_Interact_Screen` | socket | 0 |  | Rack status display |
| `SOCKET_Interact_IDReader` | socket | 0 |  | Badge / ID reader |
| `SOCKET_Interact_Sled_Top` | socket | 0 |  | Top sled handle line (others at 13.4 cm pitch) |
| `SOCKET_Interact_RearDoor` | socket | 0 |  | Rear door handle |
| `SOCKET_Mount_Floor` | socket | 0 |  | Floor pivot; seismic anchors through feet |
| `SOCKET_Cable_Top` | socket | 0 |  | Overhead cable tray drop |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 176 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_BrushedAluminum` | 1200 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 12 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_Graphite` | 1444 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 5680 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 1148 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 1524 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 176 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Sled_01`: OD_MAT_IonBlue_Emissive
- `Sled_02`: OD_MAT_IonBlue_Emissive
- `Sled_03`: OD_MAT_IonBlue_Emissive
- `Sled_04`: OD_MAT_IonBlue_Emissive
- `Sled_05`: OD_MAT_IonBlue_Emissive
- `Sled_06`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Status display** (`SOCKET_Interact_Screen`): Rack health UI
- **ID reader** (`SOCKET_Interact_IDReader`): Badge in
- **Server sleds** (`SOCKET_Interact_Sled_Top`): Slide out 0.60 m along +X
- **Rear door** (`SOCKET_Interact_RearDoor`): Opens 110 deg

## Mounting points

- **Floor** (`SOCKET_Mount_Floor`): Free-standing; keep 0.9 m front and rear clearance
- **Cable** (`SOCKET_Cable_Top`): Top entry

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-50.0, -30.0, 0.0] max [50.0, 30.0, 210.0]
- Expected: min (-50.0, -30.0, 0) max (50.0, 30.0, 210)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Rubber, OD_MAT_IonBlue_Emissive, OD_MAT_Display
- GLB problems: none
- Assembly: 388 solids, 1 connected component(s), 0 interpenetration(s)
