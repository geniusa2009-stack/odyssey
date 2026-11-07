// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Deliberately small global HUD (§21): mission context, one critical warning, the interaction
// prompt, an optional objective cue, and the connection state while not ready. Engineering detail
// lives on diegetic displays in the station, not here. Layout = WBP_OdysseyHUD (editor asset);
// every bound widget is optional so the Blueprint can omit any of them.
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

	// Override in Blueprint for animation (fade a warning in, etc.).
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
