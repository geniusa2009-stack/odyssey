#include "OdysseySlidingDoor.h"

#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/Pawn.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const FName ColorParam(TEXT("EmissiveColor"));
	const FName StrengthParam(TEXT("EmissiveStrength"));

	UStaticMeshComponent* MakePart(AActor* Owner, USceneComponent* Parent, const TCHAR* Name, bool bBlock)
	{
		UStaticMeshComponent* C = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Parent);
		C->SetMobility(EComponentMobility::Movable);
		C->SetCollisionProfileName(bBlock ? TEXT("BlockAll") : TEXT("NoCollision"));
		return C;
	}

	// smootherstep: soft start, soft stop
	float Ease(float X)
	{
		X = FMath::Clamp(X, 0.f, 1.f);
		return X * X * X * (X * (X * 6.f - 15.f) + 10.f);
	}
}

AOdysseySlidingDoor::AOdysseySlidingDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	Frame = MakePart(this, Root, TEXT("Frame"), true);
	Frame->SetMobility(EComponentMobility::Static);
	PanelLeft = MakePart(this, Root, TEXT("PanelLeft"), true);
	PanelRight = MakePart(this, Root, TEXT("PanelRight"), true);
	StatusLeft = MakePart(this, Frame, TEXT("StatusLeft"), false);
	StatusRight = MakePart(this, Frame, TEXT("StatusRight"), false);

	Presence = CreateDefaultSubobject<UBoxComponent>(TEXT("Presence"));
	Presence->SetupAttachment(Root);
	Presence->SetBoxExtent(FVector(150.0, 260.0, 130.0));
	Presence->SetRelativeLocation(FVector(0.0, 0.0, 130.0));
	Presence->SetCollisionProfileName(TEXT("Trigger"));
	Presence->SetGenerateOverlapEvents(true);
}

void AOdysseySlidingDoor::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	LeftClosed = PanelLeft->GetRelativeLocation();
	RightClosed = PanelRight->GetRelativeLocation();
}

void AOdysseySlidingDoor::BeginPlay()
{
	Super::BeginPlay();
	LeftClosed = PanelLeft->GetRelativeLocation();
	RightClosed = PanelRight->GetRelativeLocation();
	if (StatusLeft->GetStaticMesh())
	{
		StatusMidL = StatusLeft->CreateDynamicMaterialInstance(0);
	}
	if (StatusRight->GetStaticMesh())
	{
		StatusMidR = StatusRight->CreateDynamicMaterialInstance(0);
	}
	State = bLocked ? EOdysseyDoorState::Locked : EOdysseyDoorState::Closed;
	ApplyPanels();
	ApplyStatus();
}

bool AOdysseySlidingDoor::IsOccupied() const
{
	TArray<AActor*> Overlaps;
	Presence->GetOverlappingActors(Overlaps, APawn::StaticClass());
	return Overlaps.Num() > 0;
}

void AOdysseySlidingDoor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const bool bOccupied = bForceOpen || IsOccupied();
	SinceOccupied = bOccupied ? 0.f : SinceOccupied + DeltaSeconds;
	const bool bWantOpen = !bLocked && (bOccupied || SinceOccupied < HoldOpenSeconds);
	const float Step = DeltaSeconds / FMath::Max(0.1f, StrokeSeconds);
	const float Before = Alpha;
	Alpha = FMath::Clamp(Alpha + (bWantOpen ? Step : -Step), 0.f, 1.f);

	if (bLocked && Alpha <= 0.f) State = EOdysseyDoorState::Locked;
	else if (Alpha >= 1.f) State = EOdysseyDoorState::Open;
	else if (Alpha <= 0.f) State = EOdysseyDoorState::Closed;
	else State = Alpha > Before ? EOdysseyDoorState::Opening : EOdysseyDoorState::Closing;

	if (Alpha != Before)
	{
		ApplyPanels();
	}
	ApplyStatus();
}

void AOdysseySlidingDoor::ApplyPanels()
{
	const float D = OpenDistance * Ease(Alpha);
	PanelLeft->SetRelativeLocation(LeftClosed - FVector(D, 0.0, 0.0));
	PanelRight->SetRelativeLocation(RightClosed + FVector(D, 0.0, 0.0));
}

void AOdysseySlidingDoor::ApplyStatus()
{
	FLinearColor C;
	float Strength = 6.f;
	switch (State)
	{
	case EOdysseyDoorState::Locked:
		C = FLinearColor(0.48f, 0.06f, 0.05f);
		Strength = 4.f + 2.f * FMath::Sin(GetWorld()->GetTimeSeconds() * 4.f);
		break;
	case EOdysseyDoorState::Opening:
	case EOdysseyDoorState::Closing:
		C = FLinearColor(0.68f, 0.32f, 0.04f);
		break;
	default:
		C = FLinearColor(0.12f, 0.52f, 0.64f);
		Strength = State == EOdysseyDoorState::Open ? 8.f : 5.f;
		break;
	}
	for (UMaterialInstanceDynamic* M : {StatusMidL.Get(), StatusMidR.Get()})
	{
		if (M)
		{
			M->SetVectorParameterValue(ColorParam, C);
			M->SetScalarParameterValue(StrengthParam, Strength);
		}
	}
}
