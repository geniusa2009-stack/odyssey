// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Startup (§6): the pawn waits (input held) until the backend session is ready, then is placed at
// the Unreal anchor of the backend's semantic location. Later snapshots never teleport the
// player: physical position is Unreal's; only the semantic location is the backend's.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"

#include "OdysseyGameMode.generated.h"

UCLASS()
class ODYSSEYPLAYER_API AOdysseyGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AOdysseyGameMode();

protected:
	virtual void BeginPlay() override;

private:
	UFUNCTION() void HandleSessionReady();
	UFUNCTION() void HandleSessionReplaced(const FString& Reason);
	void PlacePlayerAtBackendLocation();
	bool bPlaced = false;
};

UCLASS()
class ODYSSEYPLAYER_API AOdysseyPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	// Minimal HUD widget class (WBP_OdysseyHUD, child of UOdysseyHUDWidget).
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|UI") TSubclassOf<class UOdysseyHUDWidget> HUDClass;

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY() TObjectPtr<class UOdysseyHUDWidget> HUD;
};
