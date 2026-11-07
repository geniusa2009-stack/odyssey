// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseySemanticAnchor.h"

#include "Components/ArrowComponent.h"
#include "Components/SceneComponent.h"
#include "OdysseySemanticBindingComponent.h"

AOdysseySemanticAnchor::AOdysseySemanticAnchor()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Binding = CreateDefaultSubobject<UOdysseySemanticBindingComponent>(TEXT("SemanticBinding"));
#if WITH_EDITORONLY_DATA
	Arrow = CreateEditorOnlyDefaultSubobject<UArrowComponent>(TEXT("Arrow"));
	if (Arrow)
	{
		Arrow->SetupAttachment(RootComponent);
		Arrow->ArrowColor = FColor(80, 200, 255);
	}
#endif
}

FName AOdysseySemanticAnchor::GetLocationId() const
{
	return Binding ? Binding->SemanticId : NAME_None;
}
