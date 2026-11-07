// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Makes world lights visibly follow authoritative object state (§20): a room dims to standby
// when the backend reports its load shed, an equipment indicator goes dark when the equipment is
// off, a warning light is on while an incident involves the object — and everything returns
// exactly when the backend's values return, because intensities are recomputed from the mirror
// on every change (odyssey::presentation::Evaluate, natively tested against real backend state).
// It only READS the mirror; it never decides an outcome. A Blueprint event drives art hooks.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyObjectPresentationComponent.generated.h"

class ULightComponent;

// Intensity multipliers per backend value; values not listed keep full intensity.
// Backend vocabulary: power powered|off · mode off|eco|nominal|boost · status operational|offline|damaged.
USTRUCT(BlueprintType)
struct ODYSSEYWORLD_API FOdysseyLightRule
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> PowerScale;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> ModeScale;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> StatusScale;
	// Warning light: on while an active incident involves the object, otherwise off.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") bool bWarning = false;
};

// Lights placed as separate actors (room ceiling lights, indicators) that follow this object.
USTRUCT(BlueprintType)
struct ODYSSEYWORLD_API FOdysseyLightGroup
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") FName Name;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") FOdysseyLightRule Rule;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TArray<TObjectPtr<AActor>> LightActors;
};

UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYWORLD_API UOdysseyObjectPresentationComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UOdysseyObjectPresentationComponent();

	// Rule for light components on the owning actor itself (default: equipment indicator).
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	FOdysseyLightRule OwnLightRule;

	// Owner light components with this tag use the warning rule instead.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	FName WarningLightTag = TEXT("OdysseyWarning");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	TArray<FOdysseyLightGroup> LightGroups;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation", meta = (ClampMin = "0.0"))
	float BlendSeconds = 0.6f;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Presentation")
	FOdysseyObjectView GetCurrentView() const { return Current; }

	// Current target scale of a group (0..1) — for tests/debug.
	UFUNCTION(BlueprintPure, Category = "Odyssey|Presentation")
	float GetGroupScale(FName GroupName) const;

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
		int32 Group = INDEX_NONE;  // INDEX_NONE = owner light
		bool bOwnWarning = false;
		float BaseIntensity = 0.f;
		float From = 1.f;
		float To = 1.f;
	};
	TArray<FLightState> Lights;
	TMap<FName, float> GroupScale;
	FOdysseyObjectView Current;
	float BlendAlpha = 1.f;
};
