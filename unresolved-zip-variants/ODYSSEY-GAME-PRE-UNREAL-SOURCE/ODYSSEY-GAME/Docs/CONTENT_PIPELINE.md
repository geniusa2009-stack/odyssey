# Content pipeline

> No binary assets (`.uasset`/`.umap`) are in the scaffold checkpoint. Everything below that
> creates assets is UNREAL_EDITOR_VERIFICATION_REQUIRED and must be reviewed before committing.

## Principles

* C++ for architecture and systems; Blueprints for assembly and presentation (Blueprint children
  of the C++ classes: `BP_OdysseyPlayer`, `BP_PowerConsole`, `BP_Crew_*`, `WBP_*`).
* Gameplay data that originates in the backend is **generated**, never retyped
  (semantic registry, fixtures, frame schema).
* AI-driven editor work (scripts, Unreal MCP) is a development tool only, states its exact target
  before running, never touches anything else, and is experimental until reviewed (§32/§33).
  The shipped game never depends on MCP.
* Greybox means correct scale (metric, 1 uu = 1 cm, doors 260 cm, corridors 320 cm high), clean
  silhouettes, purposeful lighting and clear traversal — not careless geometry.

## Folder ownership

| Folder | Content | Producer |
|---|---|---|
| `/Game/Systems/SemanticIds/` | `DT_SemanticIds_EarthCommand` | `Tools/Editor/import_semantic_registry.py` (from the generated JSON) |
| `/Game/Systems/Input/` | `IA_Move`, `IA_Look`, `IA_Run`, `IA_Interact`, `IA_Cycle`, `IA_Back`, `IMC_Default` | hand-made in the editor |
| `/Game/Earth/EarthCommand/Maps/` | `L_EarthCommand_Slice` (7 areas) | `Tools/Editor/build_earth_command_greybox.py` from `Content/Systems/Greybox/L_EarthCommand_Slice.layout.json`, then hand-tuned (bring layout changes back into the definition) |
| `/Game/Characters/` | `BP_OdysseyPlayer` (Game Animation Sample character), `BP_Crew_Maya/Omar/Sofia/Jay` | editor |
| `/Game/UI/` | `WBP_OdysseyHUD`, `WBP_PowerConsoleDisplay`, `WBP_FutureLensDebug`, `WBP_BlackBoxDebug` | editor |
| `/Game/Dev/` | test maps, debug meshes (never cooked) | editor |
| `/Game/Moon/`, `/Game/Vehicles/` | reserved — nothing in Phase 6 | — |

## The map definition

`Content/Systems/Greybox/L_EarthCommand_Slice.layout.json` is the reviewed, text-diffable source
of the verification map: areas, doors, anchors, zones, system actors and console controls,
lights and the backend object/rule each follows, crew placeholders. Change the map there; the
greybox script, the registry generator and the native tests all read it. After editing:

```
../odyssey/.venv/bin/python Tools/SemanticIds/generate_registry.py --backend ../odyssey --write
make -C Tools/ProtocolCore test && python3 Tools/Editor/dry_run_greybox.py
```

## Regenerating backend-derived data

```
python3 Tools/Contract/sync_fixtures.py --backend ../odyssey --write                       # fixtures + PROVENANCE
../odyssey/.venv/bin/python Tools/SemanticIds/generate_registry.py --backend ../odyssey --write
../odyssey/.venv/bin/python Tools/Contract/export_realtime_schema.py --backend ../odyssey --write
# then in the editor:
py "<project>/Tools/Editor/import_semantic_registry.py"
```

Run the native tests after any regeneration; a backend contract change shows up as a failing
fixture/schema test before it reaches the game.

## Source control

`.gitignore` excludes `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`, IDE and Xcode
workspaces, `.env*`, local config, Unreal MCP temporary files and the native build directory.
`.gitattributes` routes `.uasset`, `.umap`, meshes, textures, audio, video and fonts through
Git LFS (`git lfs install` once per clone). Registry JSON, fixtures and docs stay plain text.

## Lighting and performance budget (greybox)

Lumen software GI, no hardware ray tracing, virtual shadow maps, no auto-exposure or motion blur
(DefaultEngine.ini). One sky light, a handful of point lights per room, no Nanite-dependent
assets, no World Partition (single controlled map). Scalability: test at Medium/High on the
Apple Silicon machine and record frame time in the verification report.
