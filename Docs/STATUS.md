# Phase 6 status — integration scaffold, pending Unreal Editor verification

**Phase 6 is NOT complete.** This checkpoint is the integration scaffold produced without access
to Unreal Engine (hybrid workflow). The vertical slice has not been built, compiled or played.

## Verified here (actually run)

| Item | Evidence |
|---|---|
| Protocol core compiles with Unreal-like constraints | clang++ 18 `-std=c++20 -fno-exceptions -fno-rtti -Wall -Wextra -Wshadow -Werror` (+ `-Wundef -Wimplicit-fallthrough -Wshorten-64-to-32` clean); Unreal macro-collision guard |
| Protocol behaviour against the real recorded contract | 26 cases / 959 checks pass; also under g++ ASan + UBSan |
| Protocol behaviour against a real backend process | live harness 60/60 (backend 4f7be83, uvicorn + SQLite), including REST timeout, duplicated/reordered frames, forced stale, socket drop, **backend restart**, the load-shedding strategy with Training/Laboratory shed and restored, full Earth Command → LUNA-01 authorization, second-client restore, 0 × 429 |
| Verification map definition (7 areas) | scope, registry agreement, both incident strategies fully mapped (incl. physical controls), shed/restore presentation — native tests; greybox script dry run (stubbed `unreal`) |
| Contract artifacts are the backend's | 28 files vendored with sha256 provenance; `--check` against the backend passes |
| Semantic registry = backend content + map definition | generated (34 ids, 22 required in slice, derived from the map definition); `--check` passes |
| Realtime frame schema = backend models | exported from `GameControlFrame` / `GameEventEnvelope`; `--check` passes |
| OpenAPI codegen evaluation | `cpp-ue4` actually generated from the real document and inspected |
| Python tooling | all scripts byte-compile; contract/registry/schema tools run |

## UNREAL_EDITOR_VERIFICATION_REQUIRED (written, never compiled or run)

| Area | Files |
|---|---|
| Project/targets/plugin descriptors | `Odyssey.uproject`, `Source/*.Target.cs`, `Plugins/OdysseyAPI/OdysseyAPI.uplugin` |
| Module rules | `Source/*/*.Build.cs`, `Plugins/OdysseyAPI/Source/OdysseyAPI/OdysseyAPI.Build.cs` |
| Unreal C++ (all 8 game modules + plugin module) | `Source/**` , `Plugins/OdysseyAPI/Source/OdysseyAPI/Private/OdysseyAPIModule.cpp` |
| Unreal automation tests | `Plugins/…/Private/Tests/OdysseyAPIAutomationTests.cpp`, `Source/OdysseyCore/Private/Tests/OdysseySemanticRegistryTests.cpp` |
| Config | `Config/DefaultEngine.ini`, `DefaultGame.ini`, `DefaultInput.ini` |
| Editor scripts | `Tools/Editor/import_semantic_registry.py`, `Tools/Editor/build_earth_command_greybox.py` (its data handling is dry-run tested; the UE Python API calls are not) |
| Everything that needs editor assets | DataTable asset, Input assets, `BP_*`, `WBP_*`, `L_EarthCommand_Slice`, StateTree `ST_CrewSlice`, Smart Object definitions, Game Animation Sample hookup |

Every one of these files carries the marker `UNREAL_EDITOR_VERIFICATION_REQUIRED` in its header.

## Not included (by instruction)

No Blueprint assets, maps, compiled binaries, editor screenshots, automation-test results or
claims of a successful Unreal build. No Moon, no Mars, no final art. Backend unchanged.

## Known compile-risk spots

Written against the UE 5.x API from knowledge, not compiled. If the build fails, look here first:

1. **Brace-initialised `USTRUCT`s** (`OdysseyEventRouter.cpp`, `OdysseyBackendSubsystem.cpp`):
   aggregate init of `GENERATED_BODY()` structs. Fix: assign fields individually.
2. **Build.cs module names** `StateTreeModule`, `GameplayStateTreeModule`, `SmartObjectsModule`
   (OdysseyWorld) and plugin names in `Odyssey.uproject` (`GameplayStateTree`, `SmartObjects`).
3. **HTTP API surface:** `IHttpRequest::SetTimeout`, `SetContent(TArray<uint8>&&)`, and the
   completion delegate signature `(FHttpRequestPtr, FHttpResponsePtr, bool)`.
4. **Slate paint API** in `UOdysseyBlackBoxDebugWidget::NativePaint`
   (`ToPaintGeometry(FVector2f, FSlateLayoutTransform)`, `MakeLines` with `TArray<FVector2D>`).
5. **Include paths:** `Engine/OverlapResult.h`, `Components/StateTreeComponent.h`, `IWebSocket.h`,
   `WebSocketsModule.h`, `Debug/DebugDrawService.h`.
6. **`meta=(GetOptions="GetSemanticIdOptions")`** on `FName` properties (static `UFUNCTION`s).
7. **`int64` `BlueprintReadOnly` properties** in view structs (supported in UE 5; check UHT).
8. **Config struct-map syntax** for `Environments` in `DefaultGame.ini` (if it does not load,
   set it in Project Settings and copy the saved line back).
9. **Editor Python API names** (`DataTableFunctionLibrary.fill_data_table_from_json_file`,
   `LevelEditorSubsystem.new_level`, `BoxComponent.set_box_extent`).

The protocol core is not on this list: it is standard C++ already compiled with matching
constraints.

## Decisions and open items

1. **Resolved:** Training and Laboratory are part of the verification map (approved). The map has
   exactly seven areas; both incident strategies are physically playable.
2. Token storage: unencrypted `USaveGame` in Phase 6; keychain before any public build.
3. Request budget: at automated speed the client reaches ~119 of the backend's default 120
   requests/min (one snapshot per applied command + clock sync). Human play is far below it, but
   options if it bites: defer/coalesce the post-command snapshot, or raise the server limit.
