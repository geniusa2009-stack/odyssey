// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Development-only (§27/§28): not created in Shipping builds. Draws the connection overlay and
// registers network-failure controls as console commands:
//   Odyssey.Debug.Overlay [0|1]           toggle the overlay (default on in development)
//   Odyssey.Net.LoseCommandResponse [n]   REST timeout after the server applied the command (same-key retry)
//   Odyssey.Net.DropRealtime              WebSocket disconnect → HTTP restore → resume
//   Odyssey.Net.Scramble [0|1]            duplicate + out-of-order realtime frames
//   Odyssey.Net.ForceStale                next command is sent with an outdated state version
//   Odyssey.Net.Restore                   explicit restore/resync
//   Odyssey.Net.VerifyMirror              diff the mirror against a fresh server snapshot
//   Odyssey.Act <action> [target|-] [k=v] submit a semantic intent (backend validates as usual)
//   Odyssey.Session.Forget                drop stored credentials (next start = new campaign)
// "Server restart" is exercised by restarting the backend process itself (Docs/TESTING.md).
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"

#include "OdysseyDebugSubsystem.generated.h"

class APlayerController;
class IConsoleObject;
class UCanvas;

UCLASS()
class ODYSSEYDEBUG_API UOdysseyDebugSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

private:
	// UHT does not allow UFUNCTIONs inside build-configuration #if blocks: declared always.
	UFUNCTION() void HandleVerified(int32 Count, const FString& First);
#if !UE_BUILD_SHIPPING
	void Draw(UCanvas* Canvas, APlayerController* PC);
	FDelegateHandle DrawHandle;
	TArray<IConsoleObject*> Commands;
	FString LastVerify;
#endif
	bool bOverlay = true;
};
