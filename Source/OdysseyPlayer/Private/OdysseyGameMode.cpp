// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyGameMode.h"

#include "Blueprint/UserWidget.h"
#include "Components/InputComponent.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMemory.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "OdysseyHoloTable.h"
#include "OdysseySlidingDoor.h"
#include "UnrealClient.h"
#include "Engine/World.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyCore.h"
#include "OdysseyHUDWidget.h"
#include "OdysseyPlayerCharacter.h"
#include "OdysseyInteractableComponent.h"
#include "OdysseyInteractorComponent.h"
#include "OdysseyTouchControls.h"
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
	if (UOdysseyBackendSubsystem::IsOfflineDemo())
	{
		return;  // judge offline demo: no session will arrive; the station is explorable from PlayerStart
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

void AOdysseyPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	if (InputComponent)
	{
		InputComponent->BindKey(EKeys::F10, IE_Pressed, this, &AOdysseyPlayerController::ReturnToOrbit);
		InputComponent->BindKey(EKeys::Gamepad_Special_Right, IE_Pressed, this, &AOdysseyPlayerController::ReturnToOrbit);
		InputComponent->BindKey(EKeys::Android_Back, IE_Pressed, this, &AOdysseyPlayerController::ReturnToOrbit);
	}
}

void AOdysseyPlayerController::ReturnToOrbit()
{
	UE_LOG(LogOdysseyWorld, Log, TEXT("returning to orbit: %s"), *OrbitMap);
	UGameplayStatics::OpenLevel(this, FName(*OrbitMap), true, TEXT("SkipIntro"));
}

namespace
{
	struct FTourShot
	{
		const TCHAR* Name;
		FVector Loc;
		FRotator Rot;
		int32 Holo;     // -1 = leave, otherwise EOdysseyHoloState
		int32 Door;     // -1 = leave, 0 = close all, 1 = open all
		float Settle;   // seconds before the shot
	};

	const FTourShot GTour[] = {
		{TEXT("STATION_01_mcc_entry_overview"), FVector(1400, 300, 172), FRotator(-6, 90, 0), (int32)EOdysseyHoloState::EarthOverview, 0, 7.f},
		{TEXT("STATION_02_mcc_holo_earth_overview"), FVector(1060, 520, 190), FRotator(-9, 38, 0), (int32)EOdysseyHoloState::EarthOverview, -1, 3.f},
		{TEXT("STATION_03_mcc_holo_mission_planning"), FVector(1690, 470, 205), FRotator(-14, 132, 0), (int32)EOdysseyHoloState::MissionPlanning, -1, 4.f},
		{TEXT("STATION_04_mcc_holo_trajectory"), FVector(1400, 470, 230), FRotator(-16, 90, 0), (int32)EOdysseyHoloState::Trajectory, -1, 4.f},
		{TEXT("STATION_05_mcc_holo_simulation"), FVector(1120, 1010, 200), FRotator(-12, -38, 0), (int32)EOdysseyHoloState::Simulation, -1, 4.5f},
		{TEXT("STATION_06_mcc_holo_incident"), FVector(1620, 1020, 190), FRotator(-10, -128, 0), (int32)EOdysseyHoloState::Incident, -1, 3.f},
		{TEXT("STATION_07_mcc_console_wall"), FVector(1400, 640, 175), FRotator(-4, 90, 0), (int32)EOdysseyHoloState::Resolved, -1, 2.5f},
		{TEXT("STATION_08_mcc_reverse_toward_door"), FVector(1700, 1180, 210), FRotator(-10, -112, 0), (int32)EOdysseyHoloState::EarthOverview, -1, 3.f},
		{TEXT("STATION_09_corridor_doors_closed"), FVector(1980, -120, 175), FRotator(-4, 152, 0), -1, 0, 3.f},
		{TEXT("STATION_10_corridor_door_open"), FVector(1400, -60, 172), FRotator(-3, 90, 0), -1, 1, 2.f},
		{TEXT("STATION_11_training_overview"), FVector(2290, 300, 200), FRotator(-9, 46, 0), -1, 0, 3.f},
		{TEXT("STATION_12_training_simulator_zone"), FVector(2700, 430, 172), FRotator(-6, 90, 0), -1, -1, 2.f},
		{TEXT("STATION_13_training_instructor_monitoring"), FVector(2470, 360, 210), FRotator(-12, 32, 0), -1, -1, 2.f},
		{TEXT("STATION_14_engineering_overview"), FVector(3080, -330, 330), FRotator(-22, -150, 0), -1, -1, 3.f},
		{TEXT("STATION_15_engineering_power_console"), FVector(2760, -620, 190), FRotator(-14, -140, 0), -1, -1, 3.f},
	};
}

void AOdysseyPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	if (TourStep >= 0)
	{
		TickStationTour(DeltaTime);
	}
	TickTouch();
}

void AOdysseyPlayerController::TickTouch()
{
	AOdysseyPlayerCharacter* C = Cast<AOdysseyPlayerCharacter>(GetPawn());
	if (!Touch || !C)
	{
		return;
	}
	const FVector2D Move = Touch->GetMove();
	if (!Move.IsNearlyZero(0.05))
	{
		C->TouchMove(Move);
	}
	const FVector2D Look = Touch->ConsumeLook();
	if (!Look.IsNearlyZero())
	{
		C->TouchLook(Look);
	}
	const UOdysseyInteractorComponent* I = C->Interactor;
	const bool bStance = C->bInInteractionStance;
	Touch->SetButtonVisible(TEXT("use"), bStance || (I && I->GetFocused()));
	Touch->SetButtonVisible(TEXT("next"), bStance);
	Touch->SetButtonVisible(TEXT("back"), bStance);
	Touch->SetStickEnabled(!bStance);
	// the station has no UMG HUD class assigned; the touch layer carries status + prompt
	FString Prompt;
	if (const UOdysseyInteractableComponent* F = I ? I->GetFocused() : nullptr)
	{
		Prompt = F->GetPromptState() == EOdysseyPromptState::Offline && UOdysseyBackendSubsystem::IsOfflineDemo()
			? FString(TEXT("Live station link required — offline demo")) : F->PromptText.ToString();
	}
	Touch->SetStatus(UOdysseyBackendSubsystem::IsOfflineDemo() ? TEXT("EARTH COMMAND  ·  JUDGE DEMO  ·  OFFLINE") : TEXT(""), Prompt);
}

void AOdysseyPlayerController::HandleTouchButton(FName Id)
{
	AOdysseyPlayerCharacter* C = Cast<AOdysseyPlayerCharacter>(GetPawn());
	if (Id == TEXT("orbit"))
	{
		ReturnToOrbit();
	}
	else if (C && Id == TEXT("use"))
	{
		C->TouchInteract();
	}
	else if (C && Id == TEXT("next"))
	{
		C->TouchCycle();
	}
	else if (C && Id == TEXT("back"))
	{
		C->TouchBack();
	}
}

void AOdysseyPlayerController::TickStationTour(float Dt)
{
	TourClock += Dt;
	TourWait -= Dt;
	if (TourWait > 0.f)
	{
		return;
	}
	const int32 N = UE_ARRAY_COUNT(GTour);
	// odd phases: take the shot of the previous setup; even phases: set up the next shot
	const int32 Shot = TourStep / 2;
	if (TourStep % 2 == 1)
	{
		const FTourShot& S = GTour[Shot];
		const FString File = TourDir / (FString(S.Name) + TEXT(".png"));
		FScreenshotRequest::RequestScreenshot(File, false, false);
		const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
		UE_LOG(LogOdysseyWorld, Log, TEXT("station tour %s: frame %.2f ms, memory %.0f MB"), S.Name, FApp::GetDeltaTime() * 1000.0, Mem.UsedPhysical / (1024.0 * 1024.0));
		TourStep++;
		TourWait = 2.5f;  // let the screenshot write before the next move (and before quitting)
		return;
	}
	if (Shot >= N)
	{
		ConsoleCommand(TEXT("StopFPSChart"));
		UE_LOG(LogOdysseyWorld, Log, TEXT("station tour complete (%.1f s)"), TourClock);
		TourStep = -1;
		UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
		return;
	}
	const FTourShot& S = GTour[Shot];
	if (!TourCamera)
	{
		TourCamera = GetWorld()->SpawnActor<ACameraActor>(S.Loc, S.Rot);
		TourCamera->GetCameraComponent()->SetFieldOfView(80.f);
		TourCamera->GetCameraComponent()->bConstrainAspectRatio = false;
		SetViewTarget(TourCamera);
	}
	TourCamera->SetActorLocationAndRotation(S.Loc, S.Rot);
	for (TActorIterator<AOdysseyHoloTable> It(GetWorld()); It; ++It)
	{
		if (S.Holo >= 0)
		{
			It->bAutoProgram = false;
			It->bFollowBackendIncidents = false;
			It->SetState((EOdysseyHoloState)S.Holo);
		}
	}
	for (TActorIterator<AOdysseySlidingDoor> It(GetWorld()); It; ++It)
	{
		if (S.Door >= 0)
		{
			It->ForceOpen(S.Door == 1);
		}
	}
	TourStep++;
	TourWait = S.Settle;
}

void AOdysseyPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (FParse::Param(FCommandLine::Get(), TEXT("OdysseyStationTour")))
	{
		TourDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Odyssey/StationTour"));
		IFileManager::Get().MakeDirectory(*TourDir, true);
		TourStep = 0;
		TourWait = 8.f;  // let the map, shaders and the backend snapshot settle
		ConsoleCommand(TEXT("Odyssey.Debug.Overlay 0"));
		ConsoleCommand(TEXT("StartFPSChart"));
	}
	if (IsLocalController() && TourStep < 0 && UOdysseyTouchControls::ShouldUseTouch())
	{
		Touch = CreateWidget<UOdysseyTouchControls>(this, UOdysseyTouchControls::StaticClass());
		if (Touch)
		{
			auto Make = [](FName Id, const TCHAR* Label, FVector2f Anchor, FVector2f Offset, float R, bool bPrimary)
			{
				FOdysseyTouchButton B;
				B.Id = Id; B.Label = Label; B.Anchor = Anchor; B.Offset = Offset; B.Radius = R; B.bPrimary = bPrimary;
				return B;
			};
			Touch->SetButtons({
				Make(TEXT("use"), TEXT("USE"), FVector2f(1.f, 1.f), FVector2f(-0.10f, -0.13f), 0.085f, true),
				Make(TEXT("next"), TEXT("NEXT"), FVector2f(1.f, 1.f), FVector2f(-0.29f, -0.08f), 0.058f, false),
				Make(TEXT("back"), TEXT("BACK"), FVector2f(1.f, 1.f), FVector2f(-0.27f, -0.25f), 0.058f, false),
				Make(TEXT("orbit"), TEXT("ORBIT"), FVector2f(1.f, 0.f), FVector2f(-0.06f, 0.07f), 0.05f, false),
			});
			Touch->SetStickEnabled(true);
			Touch->SetLookEnabled(true);
			Touch->OnPressed.BindUObject(this, &AOdysseyPlayerController::HandleTouchButton);
			Touch->AddToViewport(20);
		}
	}
	if (IsLocalController() && HUDClass)
	{
		HUD = CreateWidget<UOdysseyHUDWidget>(this, HUDClass);
		if (HUD)
		{
			HUD->AddToViewport(0);
			if (TourStep >= 0)
			{
				HUD->SetVisibility(ESlateVisibility::Collapsed);
			}
		}
	}
}
