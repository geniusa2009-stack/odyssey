# OD_ENV_SlidingDoor - Station Sliding Door

Pressurised bi-parting sliding door that fills a 2.40 x 2.60 m wall opening: white chamfered portal frame (front and back plates around a pocket gap), header sign displays, ion header and jamb lights, jamb vents and hazard plates, ID access panels on both sides, top track and floor guide with hazard threshold, and two gunmetal leaves with reinforced glass windows, chevrons and rubber meeting seals.

Reference (visual only): `06_Station_Sliding_Door_Reference.png, 06B_Station_Sliding_Door_Interior_Frame.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 2.40 (Y) x H 2.60 (Z) x D 0.30 (X) |
| Pivot | floor: bottom-centre of the opening, centred in the wall (x = 0) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 7292 |
| Collision | Custom: frame as 3 boxes (two jambs + header); each leaf its own box (moves with the leaf). Add a trigger box for auto-open. |
| Nanite | Frame: Nanite ON. Leaves: Nanite ON (opaque) but glass is translucent - keep glass on a non-Nanite section or masked. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENV_SlidingDoor` | group | 0 |  |  |
| `Frame` | static | 3476 |  | Front/back frame plates, pocket spacers, header |
| `Tracks` | static | 728 |  | Top track and floor guide / threshold |
| `Sign_Front` | display | 12 |  | Module / access sign display (0..1 UV) |
| `Indicator_Header_Front` | emissive | 88 |  | Door state strip (idle/access/alert) |
| `Indicator_Jamb_Front` | emissive | 176 |  | Jamb edge lights |
| `AccessPanel_Front` | interactive | 12 |  | Biometric / ID access panel |
| `AccessPanel_Front_Button` | interactive | 44 | {"type": "press", "dir_ue": [-1, 0, 0], "range_cm": [0, 0.3]} |  |
| `Sign_Back` | display | 12 |  | Module / access sign display (0..1 UV) |
| `Indicator_Header_Back` | emissive | 88 |  | Door state strip (idle/access/alert) |
| `Indicator_Jamb_Back` | emissive | 176 |  | Jamb edge lights |
| `AccessPanel_Back` | interactive | 12 |  | Biometric / ID access panel |
| `AccessPanel_Back_Button` | interactive | 44 | {"type": "press", "dir_ue": [1, 0, 0], "range_cm": [0, 0.3]} |  |
| `Frame_Lights` | emissive | 440 |  | Frame LEDs |
| `Panel_L` | movable | 992 | {"type": "slide", "dir_ue": [0, 1, 0], "travel_cm": 100, "note": "retracts into the wall pocket (ease-in-out ~1.2 s)"} | Door leaf (gunmetal, reinforced glass window) |
| `Panel_R` | movable | 992 | {"type": "slide", "dir_ue": [0, -1, 0], "travel_cm": 100, "note": "retracts into the wall pocket (ease-in-out ~1.2 s)"} | Door leaf (gunmetal, reinforced glass window) |
| `SOCKET_Interact_Access_Front` | socket | 0 |  | Front access panel |
| `SOCKET_Interact_Access_Back` | socket | 0 |  | Back access panel |
| `SOCKET_Trigger_Centre` | socket | 0 |  | Auto-open trigger volume centre (box 3.0 x 2.4 x 2.3 m) |
| `SOCKET_Mount_Opening` | socket | 0 |  | Pivot: bottom-centre of the wall opening |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 328 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 264 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 480 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Display` | 48 | #09131C | 0.0 | 0.12 |  |
| `OD_MAT_Glass` | 56 | #9FB7BF | 0.0 | 0.04 |  |
| `OD_MAT_Graphite` | 1960 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 1828 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 1600 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 704 | #61BED2 | 0.0 | 0.3 | yes |
| `OD_MAT_Rubber` | 24 | #141618 | 0.0 | 0.88 |  |

## Emissive components

- `Indicator_Header_Front`: OD_MAT_IonBlue_Emissive
- `Indicator_Jamb_Front`: OD_MAT_IonBlue_Emissive
- `AccessPanel_Front_Button`: OD_MAT_Amber_Emissive
- `Indicator_Header_Back`: OD_MAT_IonBlue_Emissive
- `Indicator_Jamb_Back`: OD_MAT_IonBlue_Emissive
- `AccessPanel_Back_Button`: OD_MAT_Amber_Emissive
- `Frame_Lights`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive
- `Panel_L`: OD_MAT_IonBlue_Emissive
- `Panel_R`: OD_MAT_IonBlue_Emissive

## Interaction points

- **Access panel (front)** (`SOCKET_Interact_Access_Front`): ID / open / lock
- **Access panel (back)** (`SOCKET_Interact_Access_Back`): ID / open / lock
- **Auto-open** (`SOCKET_Trigger_Centre`): Proximity trigger

## Mounting points

- **Wall opening** (`SOCKET_Mount_Opening`): Sits in the 2.40 x 2.60 cut; wall pockets 1.00 m each side for full retraction

## Notes

- Reference sheet quotes 3.20 x 2.40 x 0.42 m; this follows the prototype contract 2.40 x 2.60 x 0.30 m.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-15.0, -120.0, 0.0] max [15.0, 120.0, 260.0]
- Expected: min (-15.0, -120.0, 0) max (15.0, 120.0, 260)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Display, OD_MAT_IonBlue_Emissive, OD_MAT_Amber_Emissive, OD_MAT_Glass, OD_MAT_Rubber
- GLB problems: none
- Assembly: 317 solids, 1 connected component(s), 0 interpenetration(s)
