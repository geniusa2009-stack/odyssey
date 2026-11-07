# Semantic ids

Backend ids (`earth.command.engineering.power_bus_b`) are the only names the game and the backend
share. Unreal never invents them and never types them into free Blueprint strings.

## Source of truth and pipeline

```
backend content (app/game/content/data/worlds/earth_command.yaml, narrative.yaml)
   │  Tools/SemanticIds/generate_registry.py --backend ../odyssey --write      (verified)
   ▼
Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json   (Unreal DataTable JSON format, 34 rows)
   │  Tools/Editor/import_semantic_registry.py  (editor)        UNREAL_EDITOR_VERIFICATION_REQUIRED
   ▼
/Game/Systems/SemanticIds/DT_SemanticIds_EarthCommand          (row struct FOdysseySemanticIdRow)
   │  UOdysseyBackendSettings::SemanticIdTable
   ▼
UOdysseySemanticRegistry (GameInstanceSubsystem) ──▶ odyssey::SemanticRegistry (the natively tested class)
```

`RequiredInSlice` and `Binding` are not hand-maintained: an id is required exactly when the
verification map definition (`Content/Systems/Greybox/L_EarthCommand_Slice.layout.json`) binds an
actor to it, and `Binding` is that actor's label. `generate_registry.py --check` fails when the
JSON no longer matches the backend content **or** the map definition; a map binding for an id the
backend does not define is an error. Hidden
content (incidents) is never exported: incident ids reach the client only through events, after
they have happened.

## Row format

| Column | Meaning |
|---|---|
| `Name` / `Id` | the backend id (identical; DataTable row name) |
| `Kind` | `location` · `object` · `container` · `crew` |
| `World` | `earth_command` (empty for crew) |
| `DisplayName` | backend content name (debug/editor only; player text comes from string tables) |
| `Location` | containing location for objects/containers |
| `Binding` | recommended greybox actor name (informational) |
| `RequiredInSlice` | the slice map must contain an actor bound to it |

Required in the slice (22): the six locations `observation_deck`, `mission_control`,
`engineering`, `hangar`, `training`, `laboratory`; objects `power_bus_b`, `station_battery`,
`thermal_plant`, `air_handling`, `water_systems`, `mission_control.consoles`,
`observation_deck.lunar_telescope`, `hangar.luna01`, `training.simulator`,
`laboratory.sample_analyzer`; containers `engineering.spares_locker`, `player_kit`; crew `maya`,
`omar`, `sofia`, `jay`. Every semantic target of both power-incident strategies is among them
(test `PowerIncidentStrategiesAreFullyMapped`).

## Binding actors to ids

`UOdysseySemanticBindingComponent::SemanticId` is an `FName` edited through a dropdown of the
registry's row names (`meta=(GetOptions)`). Anchors, zones, system actors, the power console and
crew placeholders all carry one. `UOdysseyWorldSubsystem` indexes them per map and logs every
`RequiredInSlice` id without an actor (`GetMissingRequiredIds()`).

Locations → `AOdysseySemanticAnchor` (spawn/arrival transform) + `AOdysseySemanticZone`
(trigger volume that reports `world.zone_entered`). The *Main Corridor* has no backend location:
it is pure Unreal traversal space and carries no zone.

## Unknown ids

The backend may send ids this build does not know (newer content, or another world — e.g. the
LUNA-01 world after the campaign transition). Policy, tested natively and live:

* never a crash, never invented presentation: the id is simply not presented;
* reported once per id (`OnUnknownSemanticIds`, log line);
* the mirror still holds the data (debug overlay, future content).
