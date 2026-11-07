// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Per-map index of semantic bindings (id → actor), anchors and zones; checks that the slice map
// represents every RequiredInSlice id; tracks the backend's player location for presentation.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"

#include "OdysseyWorldSubsystem.generated.h"

class AOdysseySemanticAnchor;
class AOdysseySemanticZone;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOdysseyLocationChangedSignature, FName, Previous, FName, Current);

UCLASS()
class ODYSSEYWORLD_API UOdysseyWorldSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

	void RegisterBinding(FName Id, AActor* Actor);
	void UnregisterBinding(FName Id, AActor* Actor);

	UFUNCTION(BlueprintPure, Category = "Odyssey|World")
	AActor* FindBoundActor(FName SemanticId) const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|World")
	AOdysseySemanticAnchor* FindAnchor(FName LocationId) const;

	// RequiredInSlice ids with no actor in this map (validated at BeginPlay of a slice map).
	UFUNCTION(BlueprintPure, Category = "Odyssey|World")
	TArray<FName> GetMissingRequiredIds() const { return MissingRequired; }

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|World")
	FOdysseyLocationChangedSignature OnPlayerSemanticLocationChanged;

private:
	UFUNCTION()
	void HandleSnapshot(FName Reason);
	void ValidateSliceCoverage();
	void CheckPlayerLocation();

	TMultiMap<FName, TWeakObjectPtr<AActor>> Bindings;
	TArray<FName> MissingRequired;
	FName LastPlayerLocation;
};
