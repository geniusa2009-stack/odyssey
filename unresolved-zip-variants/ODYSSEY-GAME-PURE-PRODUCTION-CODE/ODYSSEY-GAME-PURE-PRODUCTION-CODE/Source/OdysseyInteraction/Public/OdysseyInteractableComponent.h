



#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyInteractableComponent.generated.h"

UENUM(BlueprintType)
enum class EOdysseyPromptState : uint8
{
	Hidden,        
	Available,     
	Unavailable,   
	Refreshing,    
	Pending,       
	Offline,       
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

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction", meta = (GetOptions = "GetSemanticIdOptions"))
	FName SemanticTargetId;

	
	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Interaction")
	TArray<FName> PresentedActions;

	
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

	
	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	TArray<FOdysseyInteractionView> GetOfferedActions() const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Interaction")
	EOdysseyPromptState GetPromptState() const { return PromptState; }

	
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Interaction")
	int64 RequestAction(FName Action, const TArray<FOdysseyIntentParam>& Params);

	
	void SetFocused(bool bFocused);
	void Activate();
	bool IsFocused() const { return bIsFocused; }

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyPromptSignature OnPromptStateChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyActionResolvedSignature OnActionResolved;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyFocusSignature OnFocusChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Interaction") FOdysseyActivatedSignature OnActivatedEvent;

	
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
