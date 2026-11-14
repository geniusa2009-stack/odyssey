# Compile fixes (UE 5.8.4, OdysseyEditor Mac Development arm64)

## Fix 1 — Pre-existing UE 5.8 scaffold compile fix — overloaded virtual name collision
- Error: Source/OdysseyInteraction/Public/OdysseyInteractableComponent.h:76:7: error: 'UOdysseyInteractableComponent::Activate' hides overloaded virtual function [-Werror,-Woverloaded-virtual]
  (note: Engine/Classes/Components/ActorComponent.h:580 `ENGINE_API virtual void Activate(bool bReset=false);`)
- Origin: scaffold commit 6e7ea6d (pre-existing), not the Engineering slice.
- Fix: rename the non-virtual, non-UFUNCTION `UOdysseyInteractableComponent::Activate()` → `ActivateInteraction()`
  (declaration .h:76, definition .cpp:97, sole caller OdysseyInteractorComponent.cpp:97). No BP/backend/semantic change;
  UActorComponent::Activate(bool) untouched. `using` the base overload was rejected: `Activate()` would become ambiguous.

## Fix 2 — Engineering slice (new code): OdysseyEngineeringSliceTest.cpp, UE 5.8 JSON key type
- Error: OdysseyEngineeringSliceTest.cpp:91:38: no matching member function for call to 'Add' — no known conversion from 'const UE::TSharedString<char16_t>' to 'const FString'
- Cause: UE 5.8 FJsonObject::Values is TMap<FStringType, …> with FStringType = TSharedString (Json/Public/Dom/JsonObject.h:309).
- Fix: `FString(*P.Key)` (TSharedString::operator* → const TCHAR*).

## Fix 3 — Engineering slice (new code): missing include
- Error: OdysseyEngineeringSliceTest.cpp:217:29: member access into incomplete type 'UBoxComponent' (OdysseySemanticZone.h only forward-declares it)
- Fix: `#include "Components/BoxComponent.h"` in the test.

## Note — cascades of Fix 1
Errors in OdysseyPlayerCharacter.cpp / OdysseyPowerConsole.h / OdysseyInteractorComponent.h ("member 'UOdysseyInteractableComponent' has the same name as its class", "class member cannot be redeclared", Z_Construct_* not in global namespace, "non-friend class member … qualified name") all follow inclusion of OdysseyInteractableComponent.h in the same TU, after the -Woverloaded-virtual error; expected to clear with Fix 1 (verified in run 2).

## Fix 4 — Pre-existing scaffold link fix — missing UMG module dependency
- Error (link libUnrealEditor-OdysseyPlayer.dylib): Undefined symbols Z_Construct_UClass_UUserWidget, UUserWidget::AddToViewport(int), UUserWidget::CreateWidgetInstance(...) referenced from OdysseyGameMode.cpp.o (AOdysseyPlayerController::BeginPlay creates the HUD widget).
- Cause: OdysseyPlayer reaches UMG only through OdysseyUI's public dependency, which gives headers but not the link.
- Fix: add "UMG" to OdysseyPlayer.Build.cs PrivateDependencyModuleNames. No code/semantic change.
