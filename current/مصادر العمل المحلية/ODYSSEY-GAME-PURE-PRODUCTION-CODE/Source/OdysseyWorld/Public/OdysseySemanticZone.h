



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

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey", meta = (ClampMin = "0.0"))
	float DwellSeconds = 0.35f;

	UFUNCTION(BlueprintPure, Category = "Odyssey")
	FName GetLocationId() const;

	
	void NotifyBackendLocation(bool bPlayerIsHere) { OnBackendLocationChanged(bPlayerIsHere); }

protected:
	virtual void BeginPlay() override;

	UFUNCTION()
	void HandleBeginOverlap(UPrimitiveComponent* Overlapped, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex, bool bFromSweep, const FHitResult& Hit);
	UFUNCTION()
	void HandleEndOverlap(UPrimitiveComponent* Overlapped, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex);

	
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
