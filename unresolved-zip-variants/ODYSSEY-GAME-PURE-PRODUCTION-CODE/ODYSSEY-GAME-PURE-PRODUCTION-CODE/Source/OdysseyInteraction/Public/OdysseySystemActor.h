



#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "OdysseySystemActor.generated.h"

class UStaticMeshComponent;
class UOdysseyInteractableComponent;
class UOdysseyObjectPresentationComponent;
class UOdysseySemanticBindingComponent;

UCLASS(Blueprintable)
class ODYSSEYINTERACTION_API AOdysseySystemActor : public AActor
{
	GENERATED_BODY()

public:
	AOdysseySystemActor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UStaticMeshComponent> Body;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseySemanticBindingComponent> Binding;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseyObjectPresentationComponent> Presentation;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Odyssey") TObjectPtr<UOdysseyInteractableComponent> Interactable;
};
