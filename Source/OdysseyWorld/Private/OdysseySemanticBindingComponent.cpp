// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseySemanticBindingComponent.h"

#include "Engine/DataTable.h"
#include "OdysseyBackendSettings.h"
#include "OdysseyWorldSubsystem.h"

UOdysseySemanticBindingComponent::UOdysseySemanticBindingComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

TArray<FName> UOdysseySemanticBindingComponent::GetSemanticIdOptions()
{
	// Editor dropdown: the registry DataTable's row names (no game instance in the editor).
	TArray<FName> Names;
	if (const UDataTable* Table = GetDefault<UOdysseyBackendSettings>()->SemanticIdTable.LoadSynchronous())
	{
		Names = Table->GetRowNames();
		Names.Sort(FNameLexicalLess());
	}
	return Names;
}

void UOdysseySemanticBindingComponent::BeginPlay()
{
	Super::BeginPlay();
	if (UOdysseyWorldSubsystem* W = GetWorld()->GetSubsystem<UOdysseyWorldSubsystem>())
	{
		W->RegisterBinding(SemanticId, GetOwner());
	}
}

void UOdysseySemanticBindingComponent::EndPlay(const EEndPlayReason::Type Reason)
{
	if (UOdysseyWorldSubsystem* W = GetWorld()->GetSubsystem<UOdysseyWorldSubsystem>())
	{
		W->UnregisterBinding(SemanticId, GetOwner());
	}
	Super::EndPlay(Reason);
}
