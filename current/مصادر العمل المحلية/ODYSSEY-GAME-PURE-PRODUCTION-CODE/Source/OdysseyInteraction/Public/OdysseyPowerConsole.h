






#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "OdysseyBackendTypes.h"

#include "OdysseyPowerConsole.generated.h"

class UStaticMeshComponent;
class UWidgetComponent;
class UOdysseyInteractableComponent;
class UOdysseyObjectPresentationComponent;
class UOdysseySemanticBindingComponent;


USTRUCT(BlueprintType)
struct ODYSSEYINTERACTION_API FOdysseyConsoleControl
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") FName Action;           
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") FName TargetOverride;   
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyIntentParam> Params;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") FText Label;            
};


USTRUCT(BlueprintType)
struct ODYSSEYINTERACTION_API FOdysseyConsoleControlState
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FOdysseyConsoleControl Control;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bOffered = false;    
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bAvailable = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Reason;
};

UCLASS(Blueprintable)
class ODYSSEYINTERACTION_API AOdysseyPowerConsole : public AActor
{
	GENERATED_BODY()

public:
	AOdysseyPowerConsole();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UStaticMeshComponent> Body;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UWidgetComponent> Display;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseySemanticBindingComponent> Binding;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseyInteractableComponent> Interactable;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseyObjectPresentationComponent> Presentation;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyConsoleControl> Controls;

	UFUNCTION(BlueprintPure, Category = "Odyssey") TArray<FOdysseyConsoleControlState> GetControlStates() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey") bool IsPanelActive() const { return bPanelActive; }

	
	UFUNCTION(BlueprintCallable, Category = "Odyssey") int64 PressControl(int32 Index);
	UFUNCTION(BlueprintCallable, Category = "Odyssey") void SetPanelActive(bool bActive);

	
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey") void OnPanelActiveChanged(bool bActive);
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey") void OnControlsChanged(const TArray<FOdysseyConsoleControlState>& States);
	UFUNCTION(BlueprintImplementableEvent, Category = "Odyssey") void OnControlResolved(int32 Index, const FOdysseyCommandResolution& Resolution);

protected:
	virtual void BeginPlay() override;

private:
	UFUNCTION() void HandleActivated();
	UFUNCTION() void HandleFocus(bool bFocused);
	UFUNCTION() void HandleResolved(const FOdysseyCommandResolution& R);
	UFUNCTION() void HandleAnyChange(FName Id);
	UFUNCTION() void HandleSnapshot(FName Reason);
	void PublishControls();

	TMap<int64, int32> PendingControls;
	bool bPanelActive = false;
};
