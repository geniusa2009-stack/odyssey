




#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "OdysseyBackendTypes.h"
#include "OdysseyEventTypes.h"

#include "OdysseyHUDWidget.generated.h"

class UTextBlock;

UCLASS(Abstract)
class ODYSSEYUI_API UOdysseyHUDWidget : public UUserWidget
{
	GENERATED_BODY()

protected:
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> MissionContext;
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> CriticalWarning;
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> InteractionPrompt;
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> ObjectiveCue;
	UPROPERTY(meta = (BindWidgetOptional)) TObjectPtr<UTextBlock> ConnectionState;

	virtual void NativeConstruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	
	UFUNCTION(BlueprintNativeEvent, Category = "Odyssey|HUD") void Refresh();

private:
	UFUNCTION() void HandleState(EOdysseySessionState State);
	UFUNCTION() void HandleSnapshot(FName Reason);
	UFUNCTION() void HandleIncident(const FOdysseyIncidentEvent& E);
	UFUNCTION() void HandleClock(const FOdysseyClockEvent& E);
	UFUNCTION() void HandleObjective(const FOdysseyObjectiveEvent& E);
	FText PromptText() const;
	float SincePromptCheck = 0.f;
};
