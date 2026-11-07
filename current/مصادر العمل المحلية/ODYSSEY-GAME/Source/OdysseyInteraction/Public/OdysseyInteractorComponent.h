// UNREAL_EDITOR_VERIFICATION_REQUIRED
// On the player pawn: picks the interactable the player is physically facing (range, view cone,
// line of sight), focuses it, and forwards input. Purely local; no backend traffic until the
// player actually performs an action.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"

#include "OdysseyInteractorComponent.generated.h"

class UOdysseyInteractableComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyFocusTargetSignature, UOdysseyInteractableComponent*, Focused);

UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYINTERACTION_API UOdysseyInteractorComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UOdysseyInteractorComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Interaction", meta = (ClampMin = "0.0", ClampMax = "90.0"))
	float MaxViewAngleDegrees = 35.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Interaction", meta = (ClampMin = "0.02"))
	float ScanIntervalSeconds = 0.1f;

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Interaction")
	void Interact();

	// Perform one of the focused object's offered actions (index into GetOfferedActions()).
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Interaction")
	int64 PerformOfferedAction(int32 Index);

	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	UOdysseyInteractableComponent* GetFocused() const { return Focused.Get(); }

	// For the debug overlay: current semantic target.
	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	FName GetFocusedSemanticId() const;

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction")
	FOdysseyFocusTargetSignature OnFocusTargetChanged;

protected:
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	UOdysseyInteractableComponent* FindBest() const;
	TWeakObjectPtr<UOdysseyInteractableComponent> Focused;
	float SinceScan = 0.f;
};
