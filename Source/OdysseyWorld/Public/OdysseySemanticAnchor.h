// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Unreal-side spawn/arrival transform for a backend semantic location (§6: the backend says
// "earth.command.engineering"; Unreal decides where that is). One anchor per location in the map.
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
