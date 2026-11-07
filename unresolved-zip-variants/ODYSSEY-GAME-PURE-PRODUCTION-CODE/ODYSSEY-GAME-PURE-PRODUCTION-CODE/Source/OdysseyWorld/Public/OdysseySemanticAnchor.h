


#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseySemanticAnchor.generated.h"

class UArrowComponent;
class UOdysseySemanticBindingComponent;

UCLASS(Blueprintable)
class ODYSSEYWORLD_API AOdysseySemanticAnchor : public AActor
{
	GENERATED_BODY()

public:
	AOdysseySemanticAnchor();

	FName GetLocationId() const;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey")
	TObjectPtr<UOdysseySemanticBindingComponent> Binding;

#if WITH_EDITORONLY_DATA
	UPROPERTY(VisibleAnywhere, Category = "Odyssey")
	TObjectPtr<UArrowComponent> Arrow;
#endif
};
