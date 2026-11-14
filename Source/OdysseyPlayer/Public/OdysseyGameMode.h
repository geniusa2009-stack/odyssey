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

	// F10 / gamepad Start: back to orbit (the space front end, intro skipped). Unreal-only navigation.
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|Flow") FString OrbitMap = TEXT("/Game/Space/Maps/L_Odyssey_SolarTransit");
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Flow") void ReturnToOrbit();

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;

	// -OdysseyStationTour: validation photo tour of the station rooms (hologram states, doors), then quit.
	void TickStationTour(float Dt);
	int32 TourStep = -1;
	float TourClock = 0.f;
	float TourWait = 0.f;
	FString TourDir;
	UPROPERTY() TObjectPtr<class ACameraActor> TourCamera;

private:
	UPROPERTY() TObjectPtr<class UOdysseyHUDWidget> HUD;
};
