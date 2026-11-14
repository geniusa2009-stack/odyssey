# OD_ENV_WallUtilityPanel - Wall Utility Panel

Wall-mounted utility panel: gunmetal wall backplate, chamfered white frame with ion strips, recessed equipment bay holding a hinged power-access door, status display, circular power connectors and data ports, a guarded emergency switch and intake/exhaust vents.

Reference (visual only): `12_Wall_Utility_Panel.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 1.00 (Y) x H 1.20 (Z) x D 0.18 (X) |
| Pivot | wall: centre of the rear face (flush to wall) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 4176 |
| Collision | None needed (flush wall detail) or one box 0.18 x 1.00 x 1.20 for traces. |
| Nanite | Nanite ON for Body; door/guard/button/display small separate meshes. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENV_WallUtilityPanel` | group | 0 |  |  |
| `Body` | static | 3244 |  | Backplate, frame, bay, vents, connector plate |
| `StatusLights` | emissive | 464 |  | Frame ion strips and LEDs |
| `PowerAccessDoor` | movable | 320 | {"type": "hinge", "axis_ue": [0, 0, 1], "open_deg": 110, "opens_toward_ue": [1, 0, 0]} | Power access door, hinge on the +Y (viewer's left) edge |
| `Screen_Status` | display | 12 |  | Utility status display (0..1 UV) |
| `EmergencySwitch_Button` | interactive | 44 | {"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.6]} |  |
| `EmergencySwitch_Guard` | interactive | 92 | {"type": "hinge", "axis_ue": [0, 1, 0], "open_deg": 100, "opens_toward_ue": [0, 0, 1], "note": "flip-up cover hinged on its top edge"} |  |
| `SOCKET_Interact_Screen` | socket | 0 |  | Status display |
| `SOCKET_Interact_PowerDoor` | socket | 0 |  | Power access door pull |
| `SOCKET_Interact_Emergency` | socket | 0 |  | Emergency switch (lift guard, press) |
| `SOCKET_Interact_Connectors` | socket | 0 |  | Power connectors |
| `SOCKET_Mount_Wall` | socket | 0 |  | Pivot: centre of the rear face, flush to wall |
| `SOCKET_Mount_Anchor_1` | socket | 0 |  | Wall anchor through backplate corner |
| `SOCKET_Mount_Anchor_2` | socket | 0 |  | Wall anchor through backplate corner |
| `SOCKET_Mount_Anchor_3` | socket | 0 |  | Wall anchor through backplate corner |
| `SOCKET_Mount_Anchor_4` | socket | 0 |  | Wall anchor through backplate corner |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 128 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 220 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 1080 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 12 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_EmergencyRed_Emissive` | 100 | #B84743 | 0.0 | 0.35 | yes |
| `OD_MAT_Glass` | 44 | #9FB7BF | 0.0 | 0.04 |  |
| `OD_MAT_Graphite` | 724 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 1228 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 440 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 200 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_Amber_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_IonBlue_Emissive
- `EmergencySwitch_Button`: OD_MAT_EmergencyRed_Emissive
- `EmergencySwitch_Guard`: OD_MAT_EmergencyRed_Emissive

## Interaction points

- **Status display** (`SOCKET_Interact_Screen`): Utility status UI
- **Power door** (`SOCKET_Interact_PowerDoor`): Opens 110 deg
- **Emergency switch** (`SOCKET_Interact_Emergency`): Lift guard 100 deg, press button
- **Connectors** (`SOCKET_Interact_Connectors`): Plug-in point for cables/tools

## Mounting points

- **Wall** (`SOCKET_Mount_Wall`): Flush to wall; four corner anchors

## Notes

- Reference is drawn landscape; the prototype contract is portrait W 1.00 x H 1.20 m, which this follows.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [0.0, -50.0, -60.0] max [18.0, 50.0, 60.0]
- Expected: min (0, -50.0, -60.0) max (18, 50.0, 60.0)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Amber_Emissive, OD_MAT_EmergencyRed_Emissive, OD_MAT_IonBlue_Emissive, OD_MAT_Display, OD_MAT_Glass
- GLB problems: none
- Assembly: 103 solids, 1 connected component(s), 0 interpenetration(s)
