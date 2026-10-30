// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseySemanticZone.h"

#include "Components/BoxComponent.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyCore.h"
#include "OdysseySemanticBindingComponent.h"
#include "TimerManager.h"

AOdysseySemanticZone::AOdysseySemanticZone()
{
	PrimaryActorTick.bCanEverTick = false;
	Volume = CreateDefaultSubobject<UBoxComponent>(TEXT("Volume"));
	Volume->SetBoxExtent(FVector(400.f, 400.f, 200.f));
	Volume->SetCollisionProfileName(TEXT("Trigger"));
	RootComponent = Volume;
	Binding = CreateDefaultSubobject<UOdysseySemanticBindingComponent>(TEXT("SemanticBinding"));
}

FName AOdysseySemanticZone::GetLocationId() const
{
	return Binding ? Binding->SemanticId : NAME_None;
}

void AOdysseySemanticZone::BeginPlay()
{
	Super::BeginPlay();
	Volume->OnComponentBeginOverlap.AddDynamic(this, &AOdysseySemanticZone::HandleBeginOverlap);
	Volume->OnComponentEndOverlap.AddDynamic(this, &AOdysseySemanticZone::HandleEndOverlap);
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		B->OnCommandResolved.AddDynamic(this, &AOdysseySemanticZone::HandleResolutionProxy);
	}
}

bool AOdysseySemanticZone::IsLocalPlayerPawn(const AActor* Actor) const
{
	const APawn* Pawn = Cast<APawn>(Actor);
	return Pawn && Pawn->IsLocallyControlled() && Pawn->IsPlayerControlled();
}

void AOdysseySemanticZone::HandleBeginOverlap(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, int32, bool, const FHitResult&)
{
	if (IsLocalPlayerPawn(Other))
	{
		GetWorldTimerManager().SetTimer(DwellTimer, this, &AOdysseySemanticZone::ReportEntry, FMath::Max(0.01f, DwellSeconds), false);
	}
}

void AOdysseySemanticZone::HandleEndOverlap(UPrimitiveComponent*, AActor* Other, UPrimitiveComponent*, int32)
{
	if (IsLocalPlayerPawn(Other))
	{
		GetWorldTimerManager().ClearTimer(DwellTimer);
	}
}

void AOdysseySemanticZone::ReportEntry()
{
	UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this);
	const FName Location = GetLocationId();
	if (!B || Location.IsNone() || PendingIntent != 0)
	{
		return;
	}
	if (B->GetPlayerSemanticLocation() == Location)
	{
		return;  // already there according to the backend
	}
	FOdysseySemanticIntent Intent;
	Intent.Action = TEXT("world.zone_entered");
	Intent.Target = Location;
	Intent.Anchor = GetFName();
	// A zone entry that went stale is re-sent only if the location is still open (machine rule).
	PendingIntent = B->SubmitIntent(Intent);
	UE_LOG(LogOdysseyWorld, Log, TEXT("zone entered: %s (intent %lld)"), *Location.ToString(), PendingIntent);
}

void AOdysseySemanticZone::HandleResolutionProxy(const FOdysseyCommandResolution& R)
{
	if (R.LocalId != PendingIntent || R.Outcome == TEXT("stale"))
	{
		return;
	}
	PendingIntent = 0;
	if (R.Outcome != TEXT("applied") && R.Outcome != TEXT("no_change"))
	{
		// e.g. DECISION_UNAVAILABLE / access_restricted: the backend refused; the world shows it
		UE_LOG(LogOdysseyWorld, Log, TEXT("zone entry %s refused: %s %s"), *GetLocationId().ToString(), *R.ErrorCode.ToString(), *R.Reason.ToString());
	}
}
