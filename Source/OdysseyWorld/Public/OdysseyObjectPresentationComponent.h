// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Makes a bound world object visibly react to authoritative state (§20): lights dim or go dark with
// the backend's power state, warning lights follow active incidents, and a Blueprint event lets the
// art layer drive materials/audio/Niagara. It only READS the mirror; it never decides an outcome.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyObjectPresentationComponent.generated.h"

class ULightComponent;

UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYWORLD_API UOdysseyObjectPresentationComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UOdysseyObjectPresentationComponent();

	// Light intensity multiplier per backend power value ("on", "off", "degraded", "shed", …).
	// Unlisted values keep full intensity. Presentation data only.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	TMap<FName, float> PowerIntensityScale;

	// Same for the object's status ("nominal", "damaged", "offline", …), multiplied with power.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	TMap<FName, float> StatusIntensityScale;

	// Lights tagged with this component tag are warning lights: on while an incident involves the object.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	FName WarningLightTag = TEXT("OdysseyWarning");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation", meta = (ClampMin = "0.0"))
	float BlendSeconds = 0.6f;

	// Room lights placed as separate actors that follow this object's state (e.g. Engineering's
	// ceiling lights follow power bus B).
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	TArray<TObjectPtr<AActor>> ExtraLightActors;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Presentation")
	FOdysseyObjectView GetCurrentView() const { return Current; }

protected:
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// Art hook: called whenever the backend-reported state of this object changed.
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey|Presentation")
	void OnObjectStateChanged(const FOdysseyObjectView& View, bool bIncidentActive);

private:
	UFUNCTION() void HandleSystem(const FOdysseySystemStateEvent& E);
	UFUNCTION() void HandleIncident(const FOdysseyIncidentEvent& E);
	UFUNCTION() void HandleRefreshed(FName ObjectId);
	UFUNCTION() void HandleSnapshot(FName Reason);
	void Refresh();
	FName GetObjectId() const;

	struct FLightState
	{
		TWeakObjectPtr<ULightComponent> Light;
		float BaseIntensity = 0.f;
		float From = 1.f;
		float To = 1.f;
		bool bWarning = false;
	};
	TArray<FLightState> Lights;
	FOdysseyObjectView Current;
	float BlendAlpha = 1.f;
};
