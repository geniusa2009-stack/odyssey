
#include "OdysseyWorldSubsystem.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyCore.h"
#include "OdysseyEventRouter.h"
#include "OdysseySemanticAnchor.h"
#include "OdysseySemanticRegistry.h"
#include "OdysseySemanticZone.h"

void UOdysseyWorldSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(&InWorld))
	{
		if (UOdysseyEventRouter* R = B->GetEventRouter())
		{
			R->OnSnapshotApplied.AddDynamic(this, &UOdysseyWorldSubsystem::HandleSnapshot);
		}
	}
	ValidateSliceCoverage();
	CheckPlayerLocation();
}

void UOdysseyWorldSubsystem::Deinitialize()
{
	Bindings.Reset();
	Super::Deinitialize();
}

void UOdysseyWorldSubsystem::RegisterBinding(FName Id, AActor* Actor)
{
	if (!Id.IsNone() && Actor)
	{
		Bindings.AddUnique(Id, Actor);
	}
}

void UOdysseyWorldSubsystem::UnregisterBinding(FName Id, AActor* Actor)
{
	Bindings.Remove(Id, Actor);
}

AActor* UOdysseyWorldSubsystem::FindBoundActor(FName SemanticId) const
{
	TArray<TWeakObjectPtr<AActor>> Found;
	Bindings.MultiFind(SemanticId, Found);
	for (const TWeakObjectPtr<AActor>& A : Found)
	{
		if (A.IsValid() && !A->IsA<AOdysseySemanticZone>())
		{
			return A.Get();
		}
	}
	return Found.Num() > 0 && Found[0].IsValid() ? Found[0].Get() : nullptr;
}

AOdysseySemanticAnchor* UOdysseyWorldSubsystem::FindAnchor(FName LocationId) const
{
	TArray<TWeakObjectPtr<AActor>> Found;
	Bindings.MultiFind(LocationId, Found);
	for (const TWeakObjectPtr<AActor>& A : Found)
	{
		if (AOdysseySemanticAnchor* Anchor = Cast<AOdysseySemanticAnchor>(A.Get()))
		{
			return Anchor;
		}
	}
	return nullptr;
}

void UOdysseyWorldSubsystem::ValidateSliceCoverage()
{
	MissingRequired.Reset();
	UWorld* World = GetWorld();
	const UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	const UOdysseySemanticRegistry* Registry = GI ? GI->GetSubsystem<UOdysseySemanticRegistry>() : nullptr;
	
	bool bHasAnchor = false;
	for (TActorIterator<AOdysseySemanticAnchor> It(World); It; ++It)
	{
		bHasAnchor = true;
		RegisterBinding(It->GetLocationId(), *It);  
	}
	if (!Registry || !bHasAnchor)
	{
		return;
	}
	for (const FName Id : Registry->GetRequiredInSlice())
	{
		if (!Bindings.Contains(Id))
		{
			MissingRequired.Add(Id);
		}
	}
	for (const FName Id : MissingRequired)
	{
		UE_LOG(LogOdysseyWorld, Warning, TEXT("slice map has no actor for required semantic id %s"), *Id.ToString());
	}
}

void UOdysseyWorldSubsystem::HandleSnapshot(FName Reason)
{
	CheckPlayerLocation();
}

void UOdysseyWorldSubsystem::CheckPlayerLocation()
{
	const UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(GetWorld());
	const FName Current = B ? B->GetPlayerSemanticLocation() : NAME_None;
	if (Current == LastPlayerLocation)
	{
		return;
	}
	const FName Previous = LastPlayerLocation;
	LastPlayerLocation = Current;
	for (TActorIterator<AOdysseySemanticZone> It(GetWorld()); It; ++It)
	{
		const FName Id = It->GetLocationId();
		if (Id == Current || Id == Previous)
		{
			It->NotifyBackendLocation(Id == Current);
		}
	}
	OnPlayerSemanticLocationChanged.Broadcast(Previous, Current);
}
