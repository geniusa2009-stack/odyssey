


#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"

#include "OdysseySemanticBindingComponent.generated.h"

UCLASS(ClassGroup = (Odyssey), meta = (BlueprintSpawnableComponent))
class ODYSSEYWORLD_API UOdysseySemanticBindingComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UOdysseySemanticBindingComponent();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey", meta = (GetOptions = "GetSemanticIdOptions"))
	FName SemanticId;

	UFUNCTION()
	static TArray<FName> GetSemanticIdOptions();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
};
