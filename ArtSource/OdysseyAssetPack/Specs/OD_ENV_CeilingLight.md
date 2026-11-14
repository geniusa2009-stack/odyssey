# OD_ENV_CeilingLight - Ceiling Light Module (2.0 m)

Linear ceiling luminaire, 2.0 m standard module: white chamfered housing, gunmetal end caps, two ceiling brackets, recessed graphite bezel holding a drop-down emissive diffuser, ion edge strips and cap bars, side slot vents with hazard markers. Compact 1.2 m / 0.6 m variants can be made by changing the housing length in the script.

Reference (visual only): `11_Ceiling_Light_Module_Reference.png`

| Property | Value |
|---|---|
| Dimensions (m) | W 0.50 (Y) x H 0.14 (Z) x D 2.00 (X) |
| Pivot | ceiling: top-centre (ceiling flush); length along X |
| Forward / Up | +X forward (asset front), +Y right, +Z up |
| glTF mapping | gl.x = ue.x/100, gl.y = ue.z/100, gl.z = ue.y/100 (front faces +X in glTF) |
| Triangles | 2564 |
| Collision | None (ceiling fixture, out of reach). If needed: one box 2.00 x 0.50 x 0.14. |
| Nanite | Nanite ON for Body; Diffuser/StatusLights emissive meshes can stay non-Nanite. |

## Node hierarchy

| Node | Role | Tris | Motion | Note |
|---|---|---|---|---|
| `OD_ENV_CeilingLight` | group | 0 |  |  |
| `Body` | static | 2360 |  | Housing, end caps, bezel, brackets |
| `StatusLights` | emissive | 176 |  | Ion edge strips (state colour via material instance) |
| `Diffuser` | movable | 28 | {"type": "slide", "dir_ue": [0, 0, -1], "range_cm": [0, 3], "note": "drops for lamp service"} | Emissive diffuser panel (OD_MAT_Diffuser_Emissive) |
| `SOCKET_Light` | socket | 0 |  | Rect light origin (0.30 x 1.66 m), facing -Z |
| `SOCKET_Mount_Ceiling` | socket | 0 |  | Pivot: top-centre, flush to ceiling |
| `SOCKET_Mount_Bracket_A` | socket | 0 |  | Ceiling bracket anchor |
| `SOCKET_Mount_Bracket_B` | socket | 0 |  | Ceiling bracket anchor |

## Material groups

| Material | Tris | Base (sRGB) | Metallic | Roughness | Emissive |
|---|---|---|---|---|---|
| `OD_MAT_AerospaceWhite` | 44 | #D8D9D5 | 0.0 | 0.42 |  |
| `OD_MAT_Diffuser_Emissive` | 28 | #EEF2F3 | 0.0 | 0.5 | yes |
| `OD_MAT_Graphite` | 388 | #1C2025 | 0.0 | 0.58 |  |
| `OD_MAT_Gunmetal` | 1752 | #454B52 | 0.65 | 0.45 |  |
| `OD_MAT_HazardPaint` | 176 | #D69A35 | 0.0 | 0.55 |  |
| `OD_MAT_IonBlue_Emissive` | 176 | #61BED2 | 0.0 | 0.3 | yes |

## Emissive components

- `StatusLights`: OD_MAT_IonBlue_Emissive
- `Diffuser`: OD_MAT_Diffuser_Emissive

## Interaction points

- **Light state** (`SOCKET_Light`): Normal (ion) / analysis (amber) / emergency (red): swap strip MI

## Mounting points

- **Ceiling** (`SOCKET_Mount_Ceiling`): Flush; two brackets at x = +-0.70 m

## Notes

- Reference shows a 0.60 x 0.30 m section; this module follows the in-repo prototype contract (2.00 x 0.50 x 0.14 m) so it replaces SM_PROXY_CeilingLight_Linear in place.

## Validation (re-loaded GLB)

- Bounds (UE cm): min [-100.0, -25.0, -14.0] max [100.0, 25.0, 0.0]
- Expected: min (-100.0, -25.0, -14) max (100.0, 25.0, 0)
- Material slots: OD_MAT_AerospaceWhite, OD_MAT_Graphite, OD_MAT_Gunmetal, OD_MAT_HazardPaint, OD_MAT_IonBlue_Emissive, OD_MAT_Diffuser_Emissive
- GLB problems: none
- Assembly: 134 solids, 1 connected component(s), 0 interpenetration(s)
