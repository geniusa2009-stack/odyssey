# Engineering slice — Unreal validation runbook (prepared during the editor build)

Variables
```
GAME="/Users/ahmedibrahim/Desktop/كل المشاريع/ODYSSEY/النسخة الحالية/مصادر العمل المحلية/ODYSSEY-GAME"
PROJ="$GAME/Odyssey.uproject"
UE=~/TitanEngine/UE-5.8.4
S=/private/tmp/claude-501/-Users-ahmedibrahim-Desktop-------------ODYSSEY------------------------------------ODYSSEY-GAME/31e62c89-a087-4e72-9653-22be5588b86d/scratchpad
```

## 0. Build (running)
`UE_ROOT=$UE bash Tools/Mac/build_editor.sh -MaxParallelActions=2` → log `$S/build2.out`, `Logs/build-editor-latest.log`.
After the engine finishes, the same command again picks up the new project files
(OdysseyLightFixture, Tests/, Json dependency) — incremental, project modules only.

### Compile-error triage (Unreal-side only, minimal)
1. Read the FIRST error (file:line) in `Logs/build-editor-latest.log`; ignore cascades.
2. Classify: UHT (reflection macro/type) · include path · engine API signature drift · warning-as-error.
3. Check the engine header in `$UE/Engine/Source` for the real 5.8.4 signature before editing.
4. Fix only the failing line in `Source/` or `Plugins/OdysseyAPI/.../OdysseyAPIModule.cpp`.
   Never touch: `Plugins/OdysseyAPI/Source/OdysseyAPI/Public/OdysseyProtocol/*` (protocol core,
   natively verified), `Tests/Fixtures`, `Tests/Schemas`, backend snapshot, other rooms in the layout.
5. Record: error text, file:line, minimal fix, classification (pre-existing vs new Engineering code).
6. Rebuild with the same command (incremental); repeat.
Known risk spots: STATUS.md §Known compile-risk spots (brace-init USTRUCTs, HTTP delegate signature,
Slate paint, GetOptions meta, int64 BP properties, DefaultGame.ini struct-map syntax).

## 1. Map generation (headless)
```
"$UE/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PROJ" -run=pythonscript \
  -script="$GAME/Tools/Editor/generate_slice_map.py" -unattended -nullrhi -nosplash -stdout \
  > "$S/genmap.log" 2>&1
```
Expect: `34 semantic ids imported`, 7 proxy + 6 kit reports, `greybox written … (7 areas)`,
`$GAME/Saved/Odyssey/engineering_assets_report.json`.

### Expected generated assets (all must be `filter: lfs`)
- `Content/Earth/EarthCommand/Maps/L_EarthCommand_Slice.umap`
- `Content/Earth/EarthCommand/Materials/M_ODY_HardSurface.uasset`
- `Content/Earth/EarthCommand/Materials/MI_ODY_{White,Graphite,Gunmetal,Alu,Ion,Amber,Red,Screen,Diffuser}.uasset`
- `Content/Earth/EarthCommand/Engineering/Proxies/SM_PROXY_{PowerConsole,PowerBusB_Cabinet,ORION_Terminal,ServerRack_42U,CeilingLight_Linear,WallUtilityPanel,VentModule_A}.uasset`
- `Content/Earth/EarthCommand/Engineering/Kit/SM_KIT_ENG_{Floor,Walls,DoorFrame,Ceiling,Services,CorridorTransition}.uasset`
- `Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.uasset`
Unexpected extras (e.g. `__ExternalActors__/`, `__ExternalObjects__/`) → investigate before commit.

## 2. Structural checks (from the asset report + map)
- room envelope: kit bounds x ±690, y ±590 (interior 13.8 × 11.8 between 20 cm shell walls on 14 × 12 m), ceiling z 500
- every proxy: bounds == envelope, pivot planes touched, scale 1, collision box (console, cabinet, ORION, racks) / none (light, panel, vent)
- materials: 9 MI parented to M_ODY_HardSurface, sections == material slots, UV ch 0 + lightmap ch 1
- normals/winding: visual check in screenshots (inverted faces would render back-face culled → see-through boxes)

## 3. Screenshots (rendering editor)
```
"$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$PROJ" \
  -ExecutePythonScript="$GAME/Tools/Editor/capture_engineering_views.py" -nosplash -log
```
Viewpoints (world cm, pitch/yaw):
1. ENG_01_corridor_entrance (2500, 160, 170) −4/−90 — corridor transition frame, door, room beyond
2. ENG_02_power_console (2470, −820, 185) −14/−135 — Power Console proxy, Bus B cabinet on west wall, utility panel
3. ENG_03_overview_ne_corner (3130, −260, 400) −20/−140 — whole room from above the racks
4. ENG_04_ceiling_services (2450, −650, 160) +32/−40 — beams, ceiling bays, light modules, trays, coolant risers, vent module
5. ENG_05_room_to_door (2500, −1300, 175) −3/90 — door frame from inside, racks, ORION

## 4. Backend for the live test (scratch copy; snapshot stays read-only)
```
cd "$S/backend-run" && ODYSSEY_ENVIRONMENT=development ODYSSEY_DATABASE_URL="sqlite+aiosqlite:///$S/ue-verify.db" \
  ODYSSEY_AUTO_CREATE_SCHEMA=true ODYSSEY_LOG_JSON=false .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
curl -s http://127.0.0.1:8000/api/v1/ready
```

## 5. Odyssey.Slice.Engineering
```
"$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$PROJ" -game -nullrhi -unattended \
  -nosound -nosplash -ExecCmds="Automation RunTests Odyssey.Slice.Engineering" \
  -TestExit="Automation Test Queue Empty" -log -abslog="$S/slice_test.log" -ReportExportPath="$S/slice_report"
```
Covers: Anchor_Engineering / Zone_Engineering (one each, inside the room), Sys_PowerBusB bound to
earth.command.engineering.power_bus_b, DIAGNOSTIC→system.inspect, BREAKER SERVICE→repair.perform,
proxy mesh/scale/collision, capsule sweeps, walk in → out → in, backend zone entry, lights before /
during (bus_room rule + warning) / after the incident, both console presses resolved by the backend.

## 6. Regression gates
- native: `cd $S/game/Tools/ProtocolCore && rm -f build/run_tests && make test ROOT=$S/game` → 26/26
- live harness (optional): `ODYSSEY_BACKEND=$S/backend-run ./run_live.sh` (prebuilt with -Wno-c++11-narrowing) → 60/60
- snapshot: rehash → `cmp $S/backend-before.sha <new>` (baseline sha of manifest 9457b83c…)
- greybox dry run: `python3 -I Tools/Editor/dry_run_greybox.py`; proxy contract: `python3 -I Tools/Editor/odyssey_kit_geometry.py`

## 7. Commit gate
`git status --short`, `git lfs status`, `git check-attr filter` for every new binary,
`git diff --stat`; no Saved/, Intermediate/, Binaries/, DerivedDataCache/, Logs/ content.

## Proxy → reference mapping
| Proxy asset | Reference image | Envelope W×H×D cm | Pivot | Placed as |
|---|---|---|---|---|
| SM_PROXY_PowerConsole | 01_Power_Console.png | 180×125×90 | bottom-centre | Sys_PowerBusB body (bound, interactive) |
| SM_PROXY_PowerBusB_Cabinet | 02_Power_Bus_B_Cabinet.png | 120×220×60 | bottom-centre rear | PROXY_PowerBusB_Cabinet (Unreal-only) |
| SM_PROXY_ORION_Terminal | 08B_ORION_Physical_Terminal.png (+08 sheet) | 70×155×60 | bottom-centre | PROXY_ORION_Terminal_ENG |
| SM_PROXY_ServerRack_42U | 09_Server_Equipment_Rack.png | 60×210×100 | bottom-centre | PROXY_ServerRack_ENG_01..03 |
| SM_PROXY_CeilingLight_Linear | 11_Ceiling_Light_Module_Reference.png | 50×14×200 | top-centre | Engineering_Light0..3 (AOdysseyLightFixture, bus_room) |
| SM_PROXY_WallUtilityPanel | 12_Wall_Utility_Panel.png | 100×120×18 | centre of rear face | PROXY_WallUtilityPanel_ENG |
| SM_PROXY_VentModule_A | 13_Ventilation_Module.png | 140×80×40 | centre of rear face | PROXY_VentModule_ENG |
