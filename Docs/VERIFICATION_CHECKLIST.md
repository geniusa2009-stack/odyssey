# Local verification checklist — Unreal Engine 5.8 on Apple Silicon

Purpose: turn every `UNREAL_EDITOR_VERIFICATION_REQUIRED` item into an observed result. Record the
actual output for each step (copy log lines, attach the automation report, note frame times) and
bring it back for corrections. **Do not mark a step done from expectation.** A failure is useful
data: record the first error verbatim and move on where the checklist allows.

Paths below assume the engine at `/Users/Shared/Epic Games/UE_5.8` (Epic Games Launcher default)
and the two repositories side by side:

```
~/dev/odyssey        backend (commit 4f7be839a21b054b83d34151c56510fa45ba18a4)
~/dev/ODYSSEY-GAME   this project
```

```bash
export UE="/Users/Shared/Epic Games/UE_5.8"
export GAME="$HOME/dev/ODYSSEY-GAME"
export PROJ="$GAME/Odyssey.uproject"
```

---

## 0. Prerequisites

- [ ] macOS and **Xcode at the versions Epic lists for UE 5.8** (UE 5.8 release notes → Platform SDK
      upgrades). Record: `sw_vers`, `xcodebuild -version`, `xcode-select -p`.
- [ ] Xcode command line tools selected: `sudo xcode-select -s /Applications/Xcode.app` and the
      license accepted (`sudo xcodebuild -license accept`).
- [ ] UE 5.8 installed from the Epic Games Launcher. Record the exact build shown in *Help → About*.
- [ ] `git lfs install` (once per machine).
- [ ] Python ≥ 3.11 and `uv` for the backend.
- [ ] Optional for faster iteration: *Edit → Editor Preferences → Live Coding* off for the first
      full build (UHT/header changes need full builds anyway).

## 1. Native gates first (no Unreal; ~1 minute)

```bash
cd "$GAME"
python3 Tools/Contract/sync_fixtures.py --check
make -C Tools/ProtocolCore test        # needs clang++ (Xcode CLT provides it)
```

- [ ] `fixtures intact (28 files, backend 4f7be839a21b)`.
- [ ] `22/22 cases passed, 606 checks`. (On macOS, `make test-asan` needs g++; skip it. Optionally
      add `-fsanitize=address` to the clang line, since Apple clang ships ASan.)

## 2. Backend running locally

```bash
cd ~/dev/odyssey && git rev-parse HEAD            # must print 4f7be839a21b054b83d34151c56510fa45ba18a4
uv sync
ODYSSEY_AUTO_CREATE_SCHEMA=true ODYSSEY_DATABASE_URL="sqlite+aiosqlite:///./ue-verify.db" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -s http://127.0.0.1:8000/api/v1/ready
curl -s http://127.0.0.1:8000/api/game/v1/features | python3 -m json.tool | head -5
```

- [ ] ready answers 200; features show `"protocol": "odyssey.game.v1"`.
- [ ] Optional: `ODYSSEY_BACKEND=~/dev/odyssey "$GAME/Tools/ProtocolCore/run_live.sh"` on the Mac
      (uses port 8765; independent of the server above) → `LIVE HARNESS PASSED: 51/51`.

## 3. Project generation

```bash
"$UE/Engine/Build/BatchFiles/Mac/GenerateProjectFiles.sh" -project="$PROJ" -game
```

- [ ] `Odyssey (Mac).xcworkspace` is generated. Record any UBT warnings verbatim.
- [ ] Every `*.Build.cs`/`*.Target.cs` parses. If one fails, record the error. Likely spots:
      `CppStandard`, `IncludeOrderVersion`, module names `StateTreeModule`, `GameplayStateTreeModule`,
      `SmartObjectsModule`.

## 4. C++ compilation (UHT + compile)

```bash
"$UE/Engine/Build/BatchFiles/Mac/Build.sh" OdysseyEditor Mac Development -Project="$PROJ" -WaitMutex 2>&1 | tee "$GAME/Saved/build-editor.log"
```

- [ ] UHT succeeds. Record every UHT error. The places to look first are listed in
      [STATUS.md](STATUS.md#known-compile-risk-spots).
- [ ] Every module compiles: OdysseyAPI (plugin), OdysseyCore, OdysseyRealtime, OdysseyBackend,
      OdysseyWorld, OdysseyInteraction, OdysseyUI, OdysseyPlayer, OdysseyDebug.
- [ ] Record the number of warnings per module, and every error verbatim with its file:line.
- [ ] Also build the game target once: `Build.sh Odyssey Mac Development -Project="$PROJ"`.

## 5. Plugin and module load

```bash
open "$PROJ"        # or: "$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$PROJ"
```

- [ ] The editor opens without the "modules are missing or built with a different engine version" dialog.
- [ ] *Edit → Plugins*: **ODYSSEY API (odyssey.game.v1)** enabled. Enhanced Input, StateTree,
      Gameplay State Tree, Smart Objects and Gameplay Abilities are also enabled.
- [ ] Output Log filter `LogModuleManager`: no failure for any Odyssey module.
- [ ] *Project Settings → Game → ODYSSEY Backend* shows three environments; development =
      `http://127.0.0.1:8000`, `/api/game/v1`.
- [ ] Output Log on editor start: `Semantic id registry: no DataTable configured …` is EXPECTED
      before step 6. Record it.

## 6. Registry, input assets, greybox (editor content; review everything)

AI/script editor operations name their exact target first (§33).

1. **Registry** (target: `/Game/Systems/SemanticIds/DT_SemanticIds_EarthCommand` only):
   *Tools → Execute Python Script…* → `Tools/Editor/import_semantic_registry.py`
   - [ ] Log `[Odyssey] /Game/Systems/SemanticIds/DT_SemanticIds_EarthCommand: 34 semantic ids imported`.
   - [ ] Open the DataTable: 34 rows, row struct `OdysseySemanticIdRow`.
2. **Input** (target: `/Game/Systems/Input/` only, by hand): create `IA_Move` (Axis2D), `IA_Look`
   (Axis2D), `IA_Run`, `IA_Interact`, `IA_Cycle`, `IA_Back` (Digital), and `IMC_Default` with the
   mappings in [INTERACTION_SYSTEM.md](INTERACTION_SYSTEM.md#input-enhanced-input).
3. **Player Blueprint** (target: `/Game/Characters/BP_OdysseyPlayer`): a child of
   `OdysseyPlayerCharacter`. Assign the input assets. For the mesh/AnimBP, either the UE5
   mannequin with the Game Animation Sample (Motion Matching) character, or the default mannequin
   for the first pass. Record which.
4. **Game mode** (target: `/Game/Systems/BP_OdysseyGameMode`): a child of `OdysseyGameMode` with
   Default Pawn = `BP_OdysseyPlayer`, and Player Controller = a child of `OdysseyPlayerController`
   with HUD Class = `WBP_OdysseyHUD`. `WBP_OdysseyHUD` is a child of `OdysseyHUDWidget` with text
   blocks named `MissionContext`, `CriticalWarning`, `InteractionPrompt`, `ObjectiveCue`,
   `ConnectionState`.
5. **Greybox** (target: `/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice` only): run
   `Tools/Editor/build_earth_command_greybox.py`.
   - [ ] Log `[Odyssey] greybox written to …`. Record any Python exception verbatim.
   - [ ] World Outliner shows only `EarthCommandGreybox/…` folders.
   - [ ] World Settings → GameMode Override = `BP_OdysseyGameMode`.
   - [ ] Walk the map in the editor viewport and check scale, door clearance, sightlines (see
         [EARTH_COMMAND_GREYBOX.md](EARTH_COMMAND_GREYBOX.md)). Record what you changed by hand.

## 7. Startup and backend connectivity (PIE)

Backend from step 2 running. Play In Editor (Selected Viewport).

- [ ] Output Log: `ODYSSEY backend 'development' http://127.0.0.1:8000/api/game/v1 (protocol odyssey.game.v1)`.
- [ ] Session state log: `CheckingReady → LoadingFeatures → CreatingSession → ConnectingRealtime → Ready`.
- [ ] Backend log: `GET /api/v1/ready`, `GET /api/game/v1/features`, `POST /api/game/v1/sessions` 201,
      `WebSocket /api/game/v1/ws/sessions/gs_…?last_seq=0 [accepted]`.
- [ ] The dev overlay (top left) shows `connection Ready   realtime open`, a `gs_…` session id, the
      timeline, state version 1, and location `earth.command.observation_deck`.
- [ ] The player spawns at `Anchor_ObservationDeck`, facing the window: `player placed at earth.command.observation_deck`.
- [ ] No `slice map has no actor for required semantic id …` warnings. Record any.

## 8. REST test

- [ ] `Odyssey.Net.VerifyMirror` in the console → overlay `verify  mirror == server`.
- [ ] Look at the lunar telescope and interact. If it offers `system.inspect`: backend log
      `POST …/commands` 200, then `GET …/snapshot`. The overlay's last cmd shows `→ applied`.

## 9. WebSocket test

- [ ] Backend log shows exactly one accepted socket for the session.
- [ ] Walk into Mission Control and wait. Overlay `last seq` increases without a `GET …/events` in
      the backend log (events arrive on the socket).
- [ ] After 20 s idle: no disconnect (ping/pong).

## 10. Semantic action test (the Phase 6 success path)

- [ ] Walk physically into Engineering. Backend `POST …/commands` (`world.zone_entered`, target
      `earth.command.engineering`) 200. Overlay location = `earth.command.engineering`, clock = `REALTIME`.
- [ ] Backend log `POST …/sync` about every 5 s. Within about 30 s, `incident.started` arrives.
      Overlay incident = `earth.command.power_incident`, clock `DECISION_PAUSED`, HUD one-line alert.
      Engineering lights dim and the warning light turns on.
- [ ] At the power console, interact. The panel shows DIAGNOSTIC available and BREAKER SERVICE
      unavailable (reason `fault_not_diagnosed`).
- [ ] Press DIAGNOSTIC → `system.inspect` applied, `incident.updated`. BREAKER SERVICE becomes
      available after the object refresh (`GET …/objects/earth.command.engineering.power_bus_b`).
- [ ] Press BREAKER SERVICE → `repair.perform` applied. Set the clock to ACCELERATED:
      `Odyssey.Act mission.clock_set - mode=ACCELERATED`. The incident resolves,
      the lights blend back and the warning goes off.
- [ ] LUNA-01 progression becomes visible: `Sys_Luna01` access `inspection_ready`, and the
      authorization requirements are present (`GetAuthorization()`; print them from Blueprint or
      read the overlay/log).

## 11. Stale-state test

- [ ] `Odyssey.Net.ForceStale`, then perform any offered action. Log: resolution `stale`, then
      `GET …/snapshot`, then a second `POST …/commands` with a **different** `Idempotency-Key`,
      then `applied`. The mirror verifies equal afterwards.

## 12. Idempotency / REST-timeout test

- [ ] `Odyssey.Net.LoseCommandResponse 1`, then perform an action. Log:
      `[debug] dropping a command response the server applied`. The backend shows two POSTs with
      the **same** `Idempotency-Key`; the second response has `Idempotent-Replayed: true`. The
      action is applied once (state version advanced by exactly the first response).

## 13. Reconnect / restore tests

- [ ] `Odyssey.Net.Scramble 1` for about 30 s of running clock, then `Odyssey.Net.Scramble 0`.
      The overlay's `dup dropped` increases, and `VerifyMirror` → equal.
- [ ] `Odyssey.Net.DropRealtime` → overlay `Recovering`, backend `POST …/restore`, a new socket
      with `?last_seq=<n>`, then `Ready`. `VerifyMirror` → equal.
- [ ] **Backend restart:** stop uvicorn (Ctrl-C) mid-mission. The overlay goes `Recovering`, and
      the log shows restore retries with growing delays. Start uvicorn again (same command, same
      DB). The overlay returns to `Ready` and the mission continues from the authoritative state:
      same incident stage, same objects. `VerifyMirror` → equal.
- [ ] **Client restart:** stop PIE and start it again. The same `gs_…` session id appears (from
      `Saved/SaveGames/OdysseySession_development.sav`), `POST …/restore`, and the player spawns
      at the backend's location (Engineering).
- [ ] `Odyssey.Session.Forget`, then restart PIE → a new session id, starting on the Observation Deck.

## 14. Automation tests

```bash
"$UE/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor-Cmd" "$PROJ" \
  -ExecCmds="Automation RunTests Odyssey; Quit" -unattended -nullrhi -nosplash -log \
  -ReportExportPath="$GAME/Saved/AutomationReport" 2>&1 | tee "$GAME/Saved/automation.log"
```

- [ ] `Odyssey.Protocol.*`: 22 tests. Record passed/failed and the first failure's message.
- [ ] `Odyssey.Semantic.RegistryImport` passes (the DataTable importer accepts the generated JSON).
- [ ] Attach `Saved/AutomationReport/index.json`.

## 15. Earth Command greybox review

- [ ] Walk the full flow Observation Deck → corridor → Mission Control → Engineering → Hangar
      entrance at walk and at run speed: no snagging, doors clear, and the camera never clips
      walls at the 340 cm boom (probe 14 cm).
- [ ] Each zone triggers once per entry (backend log), and nothing fires in the corridor.
- [ ] Crew placeholders stand in their rooms (StateTree `ST_CrewSlice` is not authored yet;
      record whether you created one).
- [ ] Decision to record: keep the five areas only ("repair at once" strategy), or enable
      `INCLUDE_LOAD_SHED_STUBS` / add Training + Laboratory for the load-shedding strategy.

## 16. Performance (record, do not tune yet)

- [ ] `stat unit`, `stat fps` in Engineering during the incident, at Medium and at High
      scalability. Record Frame / Game / Draw / GPU ms.
- [ ] `stat memory` (or `memreport -full`). Record the peak.
- [ ] Machine (chip, RAM) and display resolution.

## What to bring back

1. The build log excerpt for every error/warning (step 4), with file:line.
2. A ✓/✗ per checkbox, and verbatim log lines for every ✗.
3. `Saved/automation.log` and `Saved/AutomationReport/index.json`.
4. The editor-side changes you made by hand (step 6), so they can be reconciled with the scripts.
5. Performance numbers (step 16).
