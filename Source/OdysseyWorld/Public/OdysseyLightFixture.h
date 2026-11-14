// Ceiling light module: a fixture mesh plus the rect light it emits. Placed by the greybox builder
// wherever the map definition gives a light a "fixture". When the light follows a backend object,
// the object's UOdysseyObjectPresentationComponent scales this actor's light component (it collects
// every ULightComponent on a light-group actor). The fixture only mirrors that intensity onto its
// emissive panel, so the visible luminaire dims together with the light it casts. It never reads
// backend state itself.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseyLightFixture.generated.h"

class URectLightComponent;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

UCLASS(Blueprintable)
class ODYSSEYWORLD_API AOdysseyLightFixture : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyLightFixture();

	// Pivot: top-centre of the fixture, flush with the ceiling. Light faces down (-Z).
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UStaticMeshComponent> Fixture;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<URectLightComponent> Light;

	// Scalar parameter on the fixture's emissive material slots that follows the light.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") FName EmissiveScaleParameter = TEXT("EmissiveScale");

	// Current emissive factor (light intensity / authored intensity), for tests and debug.
	UFUNCTION(BlueprintPure, Category = "Odyssey") float GetEmissiveFactor() const { return LastFactor; }

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;

private:
	void ApplyFactor(float Factor);

	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> EmissiveMaterials;
	float BaseIntensity = 0.f;
	float LastFactor = 1.f;
};
