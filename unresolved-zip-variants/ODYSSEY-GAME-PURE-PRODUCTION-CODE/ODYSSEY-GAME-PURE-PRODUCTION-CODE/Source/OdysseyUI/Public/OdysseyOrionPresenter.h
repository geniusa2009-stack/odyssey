



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
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FString Text;       
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FName MessageKey;   
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") int32 Priority = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") int64 SimTick = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|ORION") FName Source;       
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
