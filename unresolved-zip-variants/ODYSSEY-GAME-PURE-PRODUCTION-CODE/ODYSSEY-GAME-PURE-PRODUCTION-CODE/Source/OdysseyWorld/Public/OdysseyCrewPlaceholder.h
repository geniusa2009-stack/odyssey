




#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Character.h"
#include "OdysseyEventTypes.h"

#include "OdysseyCrewPlaceholder.generated.h"

class UOdysseySemanticBindingComponent;
class UStateTreeComponent;


UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYWORLD_API UOdysseyCrewStateComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName CrewId;
	
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName Intent;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName SemanticLocation;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") bool bIncidentActive = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName HealthBand;
	
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FString LastCueLine;

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Crew")
	TMap<FName, TObjectPtr<AActor>> LocationPoints;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Crew")
	AActor* GetCurrentLocationPoint() const;

protected:
	virtual void BeginPlay() override;

	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey|Crew")
	void OnCrewStateChanged();
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey|Crew")
	void OnCue(const FOdysseyCueEvent& Cue);

private:
	UFUNCTION() void HandleCrew(const FOdysseyCrewEvent& E);
	UFUNCTION() void HandleCue(const FOdysseyCueEvent& E);
	UFUNCTION() void HandleSnapshot(FName Reason);
	UFUNCTION() void HandleIncident(const FOdysseyIncidentEvent& E);
	void Refresh();
};

UCLASS(Blueprintable)
class ODYSSEYWORLD_API AOdysseyCrewPlaceholder : public ACharacter
{
	GENERATED_BODY()

public:
	AOdysseyCrewPlaceholder();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UOdysseySemanticBindingComponent> Binding;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UOdysseyCrewStateComponent> CrewState;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UStateTreeComponent> StateTree;
};
