// UNREAL_EDITOR_VERIFICATION_REQUIRED
// A trigger volume for one backend semantic location. When the local player physically walks in,
// it submits world.zone_entered for that location — once per entry, never per frame, and only
// when the backend's semantic location differs (the backend owns where the player "is").
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "OdysseyBackendTypes.h"

#include "OdysseySemanticZone.generated.h"

class UBoxComponent;
class UOdysseySemanticBindingComponent;

UCLASS(Blueprintable)
class ODYSSEYWORLD_API AOdysseySemanticZone : public AActor
{
	GENERATED_BODY()

public:
	AOdysseySemanticZone();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UBoxComponent> Volume;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UOdysseySemanticBindingComponent> Binding;

	// Seconds the player must stay inside before the entry is reported (avoids doorway flicker).
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey", meta = (ClampMin = "0.0"))
	float DwellSeconds = 0.35f;

	UFUNCTION(BlueprintPure, Category = "Odyssey")
	FName GetLocationId() const;

	// Called by UOdysseyWorldSubsystem when the backend's accepted player location changes.
	void NotifyBackendLocation(bool bPlayerIsHere) { OnBackendLocationChanged(bPlayerIsHere); }

protected:
	virtual void BeginPlay() override;

	UFUNCTION()
	void HandleBeginOverlap(UPrimitiveComponent* Overlapped, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex, bool bFromSweep, const FHitResult& Hit);
	UFUNCTION()
	void HandleEndOverlap(UPrimitiveComponent* Overlapped, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex);

	// Presentation hook: the backend's accepted location changed to/away from this zone.
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey")
	void OnBackendLocationChanged(bool bPlayerIsHere);

	UFUNCTION()
	void HandleResolutionProxy(const FOdysseyCommandResolution& Resolution);

private:
	void ReportEntry();
	bool IsLocalPlayerPawn(const AActor* Actor) const;

	FTimerHandle DwellTimer;
	int64 PendingIntent = 0;
};
