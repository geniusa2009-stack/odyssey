// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyGameMode.h"

#include "Blueprint/UserWidget.h"
#include "Engine/World.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyCore.h"
#include "OdysseyHUDWidget.h"
#include "OdysseyPlayerCharacter.h"
#include "OdysseySemanticAnchor.h"
#include "OdysseyWorldSubsystem.h"

AOdysseyGameMode::AOdysseyGameMode()
{
	DefaultPawnClass = AOdysseyPlayerCharacter::StaticClass();
	PlayerControllerClass = AOdysseyPlayerController::StaticClass();
}

void AOdysseyGameMode::BeginPlay()
{
	Super::BeginPlay();
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		B->OnSessionReady.AddDynamic(this, &AOdysseyGameMode::HandleSessionReady);
		B->OnSessionReplaced.AddDynamic(this, &AOdysseyGameMode::HandleSessionReplaced);
		if (B->IsSessionReady())
		{
			HandleSessionReady();  // the game instance connected before this map loaded
			return;
		}
	}
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		if (APawn* Pawn = PC->GetPawn())
		{
			Pawn->DisableInput(PC);  // "connecting to ODYSSEY" until the session is ready
		}
	}
}

void AOdysseyGameMode::HandleSessionReady()
{
	if (!bPlaced)
	{
		PlacePlayerAtBackendLocation();
	}
}

void AOdysseyGameMode::HandleSessionReplaced(const FString&)
{
	bPlaced = false;  // a new campaign starts at its own start location
}

void AOdysseyGameMode::PlacePlayerAtBackendLocation()
{
	const UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this);
	const UOdysseyWorldSubsystem* W = GetWorld()->GetSubsystem<UOdysseyWorldSubsystem>();
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	AOdysseyPlayerCharacter* Pawn = PC ? Cast<AOdysseyPlayerCharacter>(PC->GetPawn()) : nullptr;
	if (!B || !W || !Pawn)
	{
		return;
	}
	const FName Location = B->GetPlayerSemanticLocation();
	if (const AOdysseySemanticAnchor* Anchor = W->FindAnchor(Location))
	{
		Pawn->PlaceAt(Anchor->GetActorTransform());
		UE_LOG(LogOdysseyWorld, Log, TEXT("player placed at %s (%s)"), *Location.ToString(), *Anchor->GetName());
	}
	else
	{
		UE_LOG(LogOdysseyWorld, Warning, TEXT("no anchor for backend location %s; player stays at PlayerStart"), *Location.ToString());
	}
	Pawn->EnableInput(PC);
	bPlaced = true;
}

void AOdysseyPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (IsLocalController() && HUDClass)
	{
		HUD = CreateWidget<UOdysseyHUDWidget>(this, HUDClass);
		if (HUD)
		{
			HUD->AddToViewport(0);
		}
	}
}
