// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Reusable semantic interaction (§8): physical object → this component → semantic action request
// → backend → authoritative result → presentation. Which actions are legal, and why not, comes
// from the backend (mirror interactions + reasons); this component never decides an outcome.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyInteractableComponent.generated.h"

UENUM(BlueprintType)
enum class EOdysseyPromptState : uint8
{
	Hidden,        // not focused
	Available,     // at least one presented action is offered by the backend
	Unavailable,   // nothing offered right now (see the backend reasons)
	Refreshing,    // availability is being refreshed from the backend
	Pending,       // an action was sent; waiting for the authoritative result
	Offline,       // no ready session (connecting / recovering)
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyPromptSignature, EOdysseyPromptState, State);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyActionResolvedSignature, const FOdysseyCommandResolution&, Resolution);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyFocusSignature, bool, bFocused);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOdysseyActivatedSignature);

UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYINTERACTION_API UOdysseyInteractableComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UOdysseyInteractableComponent();

	// Backend object this interaction acts on. Empty = the owner's semantic binding.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction", meta = (GetOptions = "GetSemanticIdOptions"))
	FName SemanticTargetId;

	// Actions this physical object presents (inspect, repair, set_mode…). Empty = every action
	// the backend offers for the target. Availability is always the backend's.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction")
	TArray<FName> PresentedActions;

	// Local presentation requirements (the backend validates everything else).
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction", meta = (ClampMin = "50.0"))
	float InteractionRange = 220.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction")
	bool bRequireLineOfSight = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction")
	FText PromptText;

	UFUNCTION()
	static TArray<FName> GetSemanticIdOptions();

	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	FName GetTargetId() const;

	// Presented actions with the backend's availability and reasons.
	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	TArray<FOdysseyInteractionView> GetOfferedActions() const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	EOdysseyPromptState GetPromptState() const { return PromptState; }

	// Send a semantic action for this object. Returns the local intent id (0 if refused locally).
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Interaction")
	int64 RequestAction(FName Action, const TArray<FOdysseyIntentParam>& Params);

	// Called by the player's interactor.
	void SetFocused(bool bFocused);
	void ActivateInteraction();
	bool IsFocused() const { return bIsFocused; }

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyPromptSignature OnPromptStateChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyActionResolvedSignature OnActionResolved;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyFocusSignature OnFocusChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyActivatedSignature OnActivatedEvent;

	// The player engaged the object (e.g. open the physical panel / interaction stance).
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey|Interaction")
	void OnActivated();

protected:
	virtual void BeginPlay() override;

private:
	UFUNCTION() void HandleResolved(const FOdysseyCommandResolution& R);
	UFUNCTION() void HandleRefreshed(FName ObjectId);
	UFUNCTION() void HandleSystem(const FOdysseySystemStateEvent& E);
	UFUNCTION() void HandleSnapshot(FName Reason);
	UFUNCTION() void HandleSessionState(EOdysseySessionState State);
	void UpdatePrompt();

	EOdysseyPromptState PromptState = EOdysseyPromptState::Hidden;
	TSet<int64> Pending;
	bool bIsFocused = false;
};
