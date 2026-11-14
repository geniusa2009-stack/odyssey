// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyInteractorComponent.h"

#include "CollisionQueryParams.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "OdysseyInteractableComponent.h"

UOdysseyInteractorComponent::UOdysseyInteractorComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

FName UOdysseyInteractorComponent::GetFocusedSemanticId() const
{
	return Focused.IsValid() ? Focused->GetTargetId() : NAME_None;
}

void UOdysseyInteractorComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	SinceScan += DeltaTime;
	if (SinceScan < ScanIntervalSeconds)
	{
		return;
	}
	SinceScan = 0.f;
	UOdysseyInteractableComponent* Best = FindBest();
	if (Best != Focused.Get())
	{
		if (Focused.IsValid()) Focused->SetFocused(false);
		Focused = Best;
		if (Best) Best->SetFocused(true);
		OnFocusTargetChanged.Broadcast(Best);
	}
}

UOdysseyInteractableComponent* UOdysseyInteractorComponent::FindBest() const
{
	const APawn* Pawn = Cast<APawn>(GetOwner());
	const APlayerController* PC = Pawn ? Cast<APlayerController>(Pawn->GetController()) : nullptr;
	if (!PC)
	{
		return nullptr;
	}
	FVector ViewLoc;
	FRotator ViewRot;
	PC->GetPlayerViewPoint(ViewLoc, ViewRot);
	const FVector Forward = ViewRot.Vector();
	const FVector PawnLoc = Pawn->GetActorLocation();

	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(OdysseyInteractScan), false, Pawn);
	GetWorld()->OverlapMultiByObjectType(Overlaps, PawnLoc, FQuat::Identity,
		FCollisionObjectQueryParams(FCollisionObjectQueryParams::AllObjects), FCollisionShape::MakeSphere(400.f), Params);

	UOdysseyInteractableComponent* Best = nullptr;
	float BestScore = -1.f;
	const float MinDot = FMath::Cos(FMath::DegreesToRadians(MaxViewAngleDegrees));
	TSet<const AActor*> Seen;
	for (const FOverlapResult& O : Overlaps)
	{
		const AActor* A = O.GetActor();
		if (!A || Seen.Contains(A)) continue;
		Seen.Add(A);
		UOdysseyInteractableComponent* I = A->FindComponentByClass<UOdysseyInteractableComponent>();
		if (!I) continue;
		const FVector To = A->GetActorLocation() - PawnLoc;
		const float Dist = To.Size();
		if (Dist > I->InteractionRange) continue;
		const float Dot = FVector::DotProduct(Forward, (A->GetActorLocation() - ViewLoc).GetSafeNormal());
		if (Dot < MinDot) continue;
		if (I->bRequireLineOfSight)
		{
			FHitResult Hit;
			if (GetWorld()->LineTraceSingleByChannel(Hit, ViewLoc, A->GetActorLocation(), ECC_Visibility, Params) && Hit.GetActor() != A)
			{
				continue;
			}
		}
		const float Score = Dot * 2.f - Dist / I->InteractionRange;
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = I;
		}
	}
	return Best;
}

void UOdysseyInteractorComponent::Interact()
{
	if (Focused.IsValid())
	{
		Focused->ActivateInteraction();
	}
}

int64 UOdysseyInteractorComponent::PerformOfferedAction(int32 Index)
{
	if (!Focused.IsValid())
	{
		return 0;
	}
	const TArray<FOdysseyInteractionView> Offered = Focused->GetOfferedActions();
	if (!Offered.IsValidIndex(Index))
	{
		return 0;
	}
	return Focused->RequestAction(Offered[Index].Action, {});
}
