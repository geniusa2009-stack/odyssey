// UNREAL_EDITOR_VERIFICATION_REQUIRED
// ORION presentation interface (§24). Not a chatbot and never a source of truth: it only presents
// lines the backend produced (crew.cue today; WHY explanations — GET /insights/{id}/why — later).
// No model output ever changes game state from here.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "OdysseyEventTypes.h"

#include "OdysseyOrionPresenter.generated.h"

USTRUCT(BlueprintType)
struct ODYSSEYUI_API FOdysseyOrionLine
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FName Speaker;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FString Text;       // backend-authored
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FName MessageKey;   // localization key
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") int32 Priority = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") int64 SimTick = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FName Source;       // crew.cue | why
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyOrionLineSignature, const FOdysseyOrionLine&, Line);

UCLASS()
class ODYSSEYUI_API UOdysseyOrionPresenter : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	UPROPERTY(BlueprintAssignable, Category = "Odyssey|ORION") FOdysseyOrionLineSignature OnLine;

	UFUNCTION(BlueprintPure, Category = "Odyssey|ORION") TArray<FOdysseyOrionLine> GetRecentLines() const { return Recent; }

	UPROPERTY(EditAnywhere, Category = "Odyssey|ORION") int32 MaxRecent = 16;

private:
	UFUNCTION() void HandleCue(const FOdysseyCueEvent& Cue);
	TArray<FOdysseyOrionLine> Recent;
};
