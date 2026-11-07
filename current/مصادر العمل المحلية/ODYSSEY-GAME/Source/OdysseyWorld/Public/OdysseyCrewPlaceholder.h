// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Temporary crew body (mannequin) with a stable semantic identity (maya, omar, sofia, jay). The
// final MetaHuman replaces the mesh/animation Blueprint only; gameplay code keys on CrewId.
// Behaviour runs in a StateTree (asset authored in the editor: ST_CrewSlice) that reads
// UOdysseyCrewStateComponent; activities use Smart Objects (console, inspect, sit, window).
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameFramework/Character.h"
#include "OdysseyEventTypes.h"

#include "OdysseyCrewPlaceholder.generated.h"

class UOdysseySemanticBindingComponent;
class UStateTreeComponent;

// Backend crew state exposed for StateTree property bindings. Read-only mirror data.
UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYWORLD_API UOdysseyCrewStateComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName CrewId;
	// Backend intent (e.g. monitoring, assisting_repair) — StateTree selects an activity from it.
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName Intent;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName SemanticLocation;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") bool bIncidentActive = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FName HealthBand;
	// Last short line the backend cued for this crew member (presentation only).
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Crew") FString LastCueLine;

	// Where to stand per semantic location (designer-placed points; Smart Objects inside them).
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
