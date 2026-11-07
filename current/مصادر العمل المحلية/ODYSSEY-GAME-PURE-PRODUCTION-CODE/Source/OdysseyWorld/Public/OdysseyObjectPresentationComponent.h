






#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyObjectPresentationComponent.generated.h"

class ULightComponent;



USTRUCT(BlueprintType)
struct ODYSSEYWORLD_API FOdysseyLightRule
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> PowerScale;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> ModeScale;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") TMap<FName, float> StatusScale;
	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation") bool bWarning = false;
};


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

	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	FOdysseyLightRule OwnLightRule;

	
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	FName WarningLightTag = TEXT("OdysseyWarning");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation")
	TArray<FOdysseyLightGroup> LightGroups;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Presentation", meta = (ClampMin = "0.0"))
	float BlendSeconds = 0.6f;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Presentation")
	FOdysseyObjectView GetCurrentView() const { return Current; }

	
	UFUNCTION(BlueprintPure, Category = "Odyssey|Presentation")
	float GetGroupScale(FName GroupName) const;

protected:
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	
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
		int32 Group = INDEX_NONE;  
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
