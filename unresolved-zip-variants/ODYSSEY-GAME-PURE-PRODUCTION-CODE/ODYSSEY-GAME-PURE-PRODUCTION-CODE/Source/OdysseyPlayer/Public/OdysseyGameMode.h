



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
	
	UPROPERTY(EditDefaultsOnly, Category = "Odyssey|UI") TSubclassOf<class UOdysseyHUDWidget> HUDClass;

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY() TObjectPtr<class UOdysseyHUDWidget> HUD;
};
