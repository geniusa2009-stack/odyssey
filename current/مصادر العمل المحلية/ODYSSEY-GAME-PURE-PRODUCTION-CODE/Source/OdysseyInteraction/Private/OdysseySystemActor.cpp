
#include "OdysseySystemActor.h"

#include "Components/StaticMeshComponent.h"
#include "OdysseyInteractableComponent.h"
#include "OdysseyObjectPresentationComponent.h"
#include "OdysseySemanticBindingComponent.h"

AOdysseySystemActor::AOdysseySystemActor()
{
	PrimaryActorTick.bCanEverTick = false;
	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	RootComponent = Body;
	Binding = CreateDefaultSubobject<UOdysseySemanticBindingComponent>(TEXT("SemanticBinding"));
	Presentation = CreateDefaultSubobject<UOdysseyObjectPresentationComponent>(TEXT("Presentation"));
	Interactable = CreateDefaultSubobject<UOdysseyInteractableComponent>(TEXT("Interactable"));
}
