# OD_OBS_WindowFrame - Observation Deck Window Frame

Modular observation window: 15.0 x 5.1 m chamfered white base frame (0.44 m deep), two diagonal gunmetal supports with white covers splitting a central trapezoid pane from two side panes, glazing beads, deck-side head housing with ion strip and vents, sill modules with hazard plates and ion lights, jamb vents and amber markers; structural ribs on the space side.

Reference (visual only): `10_Observation_Deck_Window.png, 10B_Observation_Window_Build_Reference.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 15.00 (Y) x H 5.10 (Z) x D 0.60 (X) |
| Pivot | floor: bottom-centre of the envelope, in the glazing plane (x = 0) |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 6532 |
| Collision | Custom: frame as 4 boxes (sill, head, jambs) + 2 strut boxes; glass: one blocking box per pane. |
| Nanite | Frame/Supports: Nanite ON. Glass is translucent: not Nanite. Very large asset - split into 3 m modules in-engine if lightmap density is a concern. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_OBS_WindowFrame` | group | 0 |  |  |
| `Frame` | static | 5344 |  | Base frame ring, deck-side and space-side details |
| `StatusLights` | emissive | 968 |  | Ion/amber accent lights |
| `Supports` | static | 168 |  | Diagonal structural supports |
| `Glass_Centre` | static | 12 |  | Reinforced multi-layer glazing (OD_MAT_Glass, translucent) |
| `Glass_Side_L` | static | 20 |  | Reinforced multi-layer glazing (OD_MAT_Glass, translucent) |
| `Glass_Side_R` | static | 20 |  | Reinforced multi-layer glazing (OD_MAT_Glass, translucent) |
| `SOCKET_View_Centre` | socket | 0 |  | Look-out point / camera anchor for the deck view |
| `SOCKET_Space_Backdrop` | socket | 0 |  | Place the Earth/space backdrop beyond -X |
| `SOCKET_Mount_Opening` | socket | 0 |  | Pivot: bottom-centre, glazing plane |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 240 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Amber_Emissive` | 176 | #D69A35 | 0.0 | 0.35 | yes |
| `OD_MAT_BrushedAluminum` | 1200 | #92989E | 1.0 | 0.3 |  |
| `OD_MAT_Glass` | 52 | #9FB7BF | 0.0 | 0.04 |  |
| `OD_MAT_Graphite` | 640 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 3208 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 224 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 792 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive

## Interaction points

- **View** (`SOCKET_View_Centre`): Observation look-at

## Mounting points

- **Wall opening** (`SOCKET_Mount_Opening`): Fits a 15.0 x 5.1 m cut; frame 0.44 m deep, ribs to 0.60 m

## Notes

- Reference sheet example is 6.0 x 2.4 x 0.5 m; this follows the contract 15.0 x 5.10 x 0.60 m with the same build steps.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-30.0, -750.0, 0.0] max [30.0, 750.0, 510.0]
- Expected: min (-30.0, -750.0, 0) max (30.0, 750.0, 510)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_BrushedAluminum, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_Amber_Emissive, OD_MAT_IonBlue_Emissive, OD_MAT_Glass
- GLB problems: none
- Assembly: 264 solids, 1 connected component(s), 0 interpenetration(s)
