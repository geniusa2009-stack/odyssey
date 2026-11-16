#include "OdysseySpaceGameMode.h"

#include "Blueprint/UserWidget.h"
#include "Components/InputComponent.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/PlatformMemory.h"
#include "Misc/App.h"
#include "RHI.h"
#include "PipelineStateCache.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "OdysseyCelestialBody.h"
#include "OdysseyLogoWidget.h"
#include "OdysseySpace.h"
#include "OdysseySpaceHUDWidget.h"
#include "OdysseyTouchControls.h"
#include "OdysseyTransitDirector.h"
#include "ShaderCompiler.h"
#include "UnrealClient.h"

AOdysseySpaceGameMode::AOdysseySpaceGameMode()
{
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AOdysseySpacePlayerController::StaticClass();
	HUDClass = nullptr;
}

AOdysseySpacePlayerController::AOdysseySpacePlayerController()
{
	bShowMouseCursor = false;
	PrimaryActorTick.bTickEvenWhenPaused = true;
}

FText AOdysseySpacePlayerController::MenuLabel(int32 Index)
{
	switch (Index)
	{
	case 0: return NSLOCTEXT("OdysseySpace", "MenuMission", "BEGIN MISSION");
	case 1: return NSLOCTEXT("OdysseySpace", "MenuTransit", "SOLAR TRANSIT");
	default: return NSLOCTEXT("OdysseySpace", "MenuExit", "EXIT");
	}
}

FText AOdysseySpacePlayerController::MenuDetail(int32 Index)
{
	switch (Index)
	{
	case 0: return NSLOCTEXT("OdysseySpace", "MenuMissionDetail", "Descend to Earth Command and take your station");
	case 1: return NSLOCTEXT("OdysseySpace", "MenuTransitDetail", "Fly OTV-1 Meridian between Earth, the Moon and Mars");
	default: return NSLOCTEXT("OdysseySpace", "MenuExitDetail", "Leave ODYSSEY");
	}
}

void AOdysseySpacePlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (TActorIterator<AOdysseyTransitDirector> It(GetWorld()); It)
	{
		Director = *It;
	}
	if (Director)
	{
		SetViewTarget(Director);
		Director->SetView(EOdysseyDirectorView::Menu);
		Director->OnArrived.AddDynamic(this, &AOdysseySpacePlayerController::HandleArrived);
		SelectedBody = Director->NumBodies() > 1 ? 1 : 0;
	}
	else
	{
		UE_LOG(LogOdysseySpace, Error, TEXT("no AOdysseyTransitDirector in %s"), *GetWorld()->GetMapName());
	}

	if (IsLocalController())
	{
		HUD = CreateWidget<UOdysseySpaceHUDWidget>(this, UOdysseySpaceHUDWidget::StaticClass());
		if (HUD)
		{
			HUD->Owner = this;
			HUD->AddToViewport(5);
		}
		Logo = CreateWidget<UOdysseyLogoWidget>(this, UOdysseyLogoWidget::StaticClass());
		if (Logo)
		{
			Logo->AddToViewport(10);
		}
		if (UOdysseyTouchControls::ShouldUseTouch())
		{
			Touch = CreateWidget<UOdysseyTouchControls>(this, UOdysseyTouchControls::StaticClass());
			if (Touch)
			{
				Touch->OnPressed.BindUObject(this, &AOdysseySpacePlayerController::HandleTouchButton);
				Touch->OnTap.BindUObject(this, &AOdysseySpacePlayerController::HandleTouchTap);
				Touch->AddToViewport(20);  // above the logo so a tap can skip the intro
			}
		}
	}
	SetInputMode(FInputModeGameOnly());
	// the development diagnostics overlay belongs to the station; the space front end stays clean
	ConsoleCommand(TEXT("Odyssey.Debug.Overlay 0"));

	bCapture = FParse::Param(FCommandLine::Get(), TEXT("OdysseyCapture"));
	// -OdysseySkipIntro, or ?SkipIntro when returning from Earth Command
	bSkipIntroRequested = FParse::Param(FCommandLine::Get(), TEXT("OdysseySkipIntro")) || GetWorld()->URL.HasOption(TEXT("SkipIntro"));
	SetFlow(EOdysseySpaceFlow::Intro);  // black hold until shaders are ready, then the logo plays
	if (bCapture)
	{
		CaptureDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Odyssey/SpaceCapture"));
		IFileManager::Get().MakeDirectory(*CaptureDir, true);
		BuildCaptureTour();
		UE_LOG(LogOdysseySpace, Log, TEXT("capture tour: %d steps -> %s"), Capture.Num(), *CaptureDir);
	}
}

void AOdysseySpacePlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	check(InputComponent);
	InputComponent->BindKey(EKeys::Up, IE_Pressed, this, &AOdysseySpacePlayerController::OnUp);
	InputComponent->BindKey(EKeys::W, IE_Pressed, this, &AOdysseySpacePlayerController::OnUp);
	InputComponent->BindKey(EKeys::Gamepad_DPad_Up, IE_Pressed, this, &AOdysseySpacePlayerController::OnUp);
	InputComponent->BindKey(EKeys::Down, IE_Pressed, this, &AOdysseySpacePlayerController::OnDown);
	InputComponent->BindKey(EKeys::S, IE_Pressed, this, &AOdysseySpacePlayerController::OnDown);
	InputComponent->BindKey(EKeys::Gamepad_DPad_Down, IE_Pressed, this, &AOdysseySpacePlayerController::OnDown);
	InputComponent->BindKey(EKeys::Left, IE_Pressed, this, &AOdysseySpacePlayerController::OnLeft);
	InputComponent->BindKey(EKeys::A, IE_Pressed, this, &AOdysseySpacePlayerController::OnLeft);
	InputComponent->BindKey(EKeys::Gamepad_DPad_Left, IE_Pressed, this, &AOdysseySpacePlayerController::OnLeft);
	InputComponent->BindKey(EKeys::Right, IE_Pressed, this, &AOdysseySpacePlayerController::OnRight);
	InputComponent->BindKey(EKeys::D, IE_Pressed, this, &AOdysseySpacePlayerController::OnRight);
	InputComponent->BindKey(EKeys::Gamepad_DPad_Right, IE_Pressed, this, &AOdysseySpacePlayerController::OnRight);
	InputComponent->BindKey(EKeys::One, IE_Pressed, this, &AOdysseySpacePlayerController::OnBody1);
	InputComponent->BindKey(EKeys::Two, IE_Pressed, this, &AOdysseySpacePlayerController::OnBody2);
	InputComponent->BindKey(EKeys::Three, IE_Pressed, this, &AOdysseySpacePlayerController::OnBody3);
	InputComponent->BindKey(EKeys::Enter, IE_Pressed, this, &AOdysseySpacePlayerController::OnConfirm);
	InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AOdysseySpacePlayerController::OnConfirm);
	InputComponent->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Pressed, this, &AOdysseySpacePlayerController::OnConfirm);
	InputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &AOdysseySpacePlayerController::OnConfirm);
	InputComponent->BindKey(EKeys::Escape, IE_Pressed, this, &AOdysseySpacePlayerController::OnBack);
	InputComponent->BindKey(EKeys::Android_Back, IE_Pressed, this, &AOdysseySpacePlayerController::OnBack);
	InputComponent->BindKey(EKeys::BackSpace, IE_Pressed, this, &AOdysseySpacePlayerController::OnBack);
	InputComponent->BindKey(EKeys::Gamepad_FaceButton_Right, IE_Pressed, this, &AOdysseySpacePlayerController::OnBack);
	InputComponent->BindKey(EKeys::C, IE_Pressed, this, &AOdysseySpacePlayerController::CycleCamera);
	InputComponent->BindKey(EKeys::Gamepad_FaceButton_Top, IE_Pressed, this, &AOdysseySpacePlayerController::CycleCamera);
	InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AOdysseySpacePlayerController::Descend);
	InputComponent->BindKey(EKeys::Q, IE_Pressed, this, &AOdysseySpacePlayerController::CycleQuality);
	InputComponent->BindKey(EKeys::Gamepad_Special_Left, IE_Pressed, this, &AOdysseySpacePlayerController::CycleQuality);
	InputComponent->BindKey(EKeys::Gamepad_FaceButton_Left, IE_Pressed, this, &AOdysseySpacePlayerController::Descend);
}

void AOdysseySpacePlayerController::SetFlow(EOdysseySpaceFlow NewFlow)
{
	Flow = NewFlow;
	FlowTime = 0.f;
	UE_LOG(LogOdysseySpace, Log, TEXT("flow -> %s"), *UEnum::GetValueAsString(NewFlow));
}

float AOdysseySpacePlayerController::GetFadeToBlack() const
{
	return Flow == EOdysseySpaceFlow::Descending ? FMath::Clamp(DescendTime / 1.4f, 0.f, 1.f) : 0.f;
}

void AOdysseySpacePlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	FlowTime += DeltaTime;
	if (bAwaitingShaders)
	{
		// first launch compiles shaders on demand: keep the screen black until compilation settles
		// cooked builds (phones) compile pipeline states, not shaders: also hold for pending PSO precache
		// requests (boosted while the screen is black; capped at 20 s so streaming requests never block)
		const int32 ShaderJobs = GShaderCompilingManager ? GShaderCompilingManager->GetNumRemainingJobs() : 0;
		const bool bWaitPso = PLATFORM_ANDROID && PipelineStateCache::IsPSOPrecachingEnabled() && ShaderWait < 20.f;  // Android only: desktop unchanged
		if (bWaitPso && ShaderWait == 0.f)
		{
			PipelineStateCache::PrecachePSOsBoostToHighestPriority(true);
		}
		const int32 Jobs = ShaderJobs + (bWaitPso ? (int32)PipelineStateCache::NumActivePrecacheRequests() : 0);
		const bool bCompiling = Jobs > 0;
		ShaderWait += DeltaTime;
		if (Logo)
		{
			Logo->SetPreparing(Jobs, ShaderWait);
		}
		ShaderQuiet = bCompiling ? 0.f : ShaderQuiet + DeltaTime;
		if (ShaderQuiet > 1.0f || ShaderWait > 180.f)
		{
			bAwaitingShaders = false;
			if (PLATFORM_ANDROID) PipelineStateCache::PrecachePSOsBoostToHighestPriority(false);
			UE_LOG(LogOdysseySpace, Log, TEXT("scene ready after %.1f s"), ShaderWait);
			if (bSkipIntroRequested || !Logo)
			{
				if (Logo) Logo->bHoldBlack = false;
				SetFlow(EOdysseySpaceFlow::Menu);
			}
			else
			{
				Logo->Play(EOdysseyLogoStyle::Intro);
				FlowTime = 0.f;
			}
		}
		if (bCapture)
		{
			TickCapture(DeltaTime);
		}
		return;
	}
	UpdateTouch();
	if (Flow == EOdysseySpaceFlow::Intro && (!Logo || Logo->IsFinished() || Logo->GetSceneReveal() >= 0.999f))
	{
		SetFlow(EOdysseySpaceFlow::Menu);
	}
	if (Flow == EOdysseySpaceFlow::Descending)
	{
		DescendTime += DeltaTime;
		if (DescendTime > 1.6f && !bLevelOpened)
		{
			bLevelOpened = true;
			UE_LOG(LogOdysseySpace, Log, TEXT("opening %s"), *EarthCommandMap);
			ConsoleCommand(TEXT("Odyssey.Debug.Overlay 1"));
			UGameplayStatics::OpenLevel(this, FName(*EarthCommandMap));
		}
	}
	if (bCapture)
	{
		TickCapture(DeltaTime);
	}
}

void AOdysseySpacePlayerController::UpdateTouch()
{
	if (!Touch)
	{
		return;
	}
	const bool bTravel = Director && Director->IsTraveling();
	const bool bAligning = Director && Director->GetTelemetry().Phase == EOdysseyTransitPhase::Aligning;
	const AOdysseyCelestialBody* Cur = Director ? Director->GetBody(Director->GetCurrentBody()) : nullptr;
	const bool bAtEarth = Cur && Cur->BodyId == FName(TEXT("earth"));
	FString Layout = TEXT("none");
	if (Flow == EOdysseySpaceFlow::Menu) Layout = TEXT("menu");
	else if (Flow == EOdysseySpaceFlow::Navigation) Layout = (bTravel || bAligning) ? TEXT("travel") : bAtEarth ? TEXT("nav-earth") : TEXT("nav");
	if (Layout == TouchLayout)
	{
		return;
	}
	TouchLayout = Layout;
	TArray<FOdysseyTouchButton> B;
	auto Add = [&B](FName Id, const TCHAR* Label, FVector2f Anchor, FVector2f Offset, float R, bool bPrimary)
	{
		FOdysseyTouchButton X;
		X.Id = Id; X.Label = Label; X.Anchor = Anchor; X.Offset = Offset; X.Radius = R; X.bPrimary = bPrimary;
		B.Add(X);
	};
	if (Layout == TEXT("menu"))
	{
		Add(TEXT("quality"), TEXT("QUALITY"), FVector2f(1.f, 1.f), FVector2f(-0.06f, -0.16f), 0.05f, false);
	}
	else if (Layout.StartsWith(TEXT("nav")))
	{
		Add(TEXT("launch"), TEXT("LAUNCH"), FVector2f(1.f, 1.f), FVector2f(-0.10f, -0.12f), 0.085f, true);
		Add(TEXT("camera"), TEXT("CAMERA"), FVector2f(1.f, 1.f), FVector2f(-0.30f, -0.08f), 0.058f, false);
		Add(TEXT("menu"), TEXT("MENU"), FVector2f(0.f, 0.f), FVector2f(0.055f, 0.15f), 0.045f, false);
		if (Layout == TEXT("nav-earth"))
		{
			Add(TEXT("descend"), TEXT("DESCEND"), FVector2f(1.f, 1.f), FVector2f(-0.27f, -0.26f), 0.065f, false);
		}
	}
	Touch->SetButtons(B);
}

void AOdysseySpacePlayerController::HandleTouchButton(FName Id)
{
	if (Id == TEXT("launch")) Confirm();
	else if (Id == TEXT("camera")) CycleCamera();
	else if (Id == TEXT("descend")) Descend();
	else if (Id == TEXT("menu")) Back();
	else if (Id == TEXT("quality")) CycleQuality();
}

bool AOdysseySpacePlayerController::HandleTouchTap(FVector2f Pos, FVector2f Screen)
{
	if (Flow == EOdysseySpaceFlow::Intro)
	{
		SkipIntro();
		return true;
	}
	if (Flow == EOdysseySpaceFlow::Menu)
	{
		const int32 Item = UOdysseySpaceHUDWidget::HitMenuItem(Pos, Screen);
		if (Item != INDEX_NONE)
		{
			MenuIndex = Item;
			Confirm();
			return true;
		}
	}
	else if (Flow == EOdysseySpaceFlow::Navigation && Director && !Director->IsTraveling())
	{
		const int32 Row = UOdysseySpaceHUDWidget::HitPlannerRow(Pos, Screen, Director->NumBodies());
		if (Row != INDEX_NONE)
		{
			SelectBody(Row);
			return true;
		}
	}
	return false;
}

void AOdysseySpacePlayerController::SkipIntro()
{
	if (Flow == EOdysseySpaceFlow::Intro && Logo)
	{
		Logo->Skip();
	}
}

void AOdysseySpacePlayerController::MenuMove(int32 Delta)
{
	if (Flow == EOdysseySpaceFlow::Menu)
	{
		MenuIndex = (MenuIndex + Delta + NumMenuItems) % NumMenuItems;
	}
}

void AOdysseySpacePlayerController::OnLeft()
{
	if (Flow == EOdysseySpaceFlow::Navigation && Director && Director->NumBodies() > 0)
	{
		SelectBody((SelectedBody - 1 + Director->NumBodies()) % Director->NumBodies());
	}
}

void AOdysseySpacePlayerController::OnRight()
{
	if (Flow == EOdysseySpaceFlow::Navigation && Director && Director->NumBodies() > 0)
	{
		SelectBody((SelectedBody + 1) % Director->NumBodies());
	}
}

void AOdysseySpacePlayerController::SelectBody(int32 Index)
{
	if (Flow == EOdysseySpaceFlow::Navigation && Director && Index >= 0 && Index < Director->NumBodies())
	{
		SelectedBody = Index;
	}
}

void AOdysseySpacePlayerController::OnConfirm()
{
	if (Flow == EOdysseySpaceFlow::Intro)
	{
		SkipIntro();
		return;
	}
	Confirm();
}

void AOdysseySpacePlayerController::OnBack()
{
	if (Flow == EOdysseySpaceFlow::Intro)
	{
		SkipIntro();
		return;
	}
	Back();
}

void AOdysseySpacePlayerController::Confirm()
{
	if (Flow == EOdysseySpaceFlow::Menu)
	{
		switch (MenuIndex)
		{
		case 0:
			Descend();
			break;
		case 1:
			EnterNavigation();
			break;
		default:
			UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
			break;
		}
	}
	else if (Flow == EOdysseySpaceFlow::Navigation && Director && !Director->IsTraveling())
	{
		if (SelectedBody != Director->GetCurrentBody())
		{
			Director->BeginTravel(SelectedBody);
		}
	}
}

void AOdysseySpacePlayerController::EnterNavigation()
{
	SetFlow(EOdysseySpaceFlow::Navigation);
	if (Director)
	{
		Director->SetView(EOdysseyDirectorView::OrbitVista);
		if (SelectedBody == Director->GetCurrentBody())
		{
			SelectedBody = (SelectedBody + 1) % FMath::Max(1, Director->NumBodies());
		}
	}
}

void AOdysseySpacePlayerController::Back()
{
	if (Flow == EOdysseySpaceFlow::Navigation && Director && !Director->IsTraveling() && Director->GetTelemetry().Phase != EOdysseyTransitPhase::Aligning)
	{
		SetFlow(EOdysseySpaceFlow::Menu);
		Director->SetView(EOdysseyDirectorView::Menu);
	}
}

void AOdysseySpacePlayerController::CycleCamera()
{
	if (Flow == EOdysseySpaceFlow::Navigation && Director && !Director->IsTraveling())
	{
		Director->SetView(Director->GetView() == EOdysseyDirectorView::OrbitVista ? EOdysseyDirectorView::PlanetView : EOdysseyDirectorView::OrbitVista);
	}
}

void AOdysseySpacePlayerController::Descend()
{
	if (Flow == EOdysseySpaceFlow::Descending || !Director || Director->IsTraveling())
	{
		return;
	}
	const AOdysseyCelestialBody* B = Director->GetBody(Director->GetCurrentBody());
	const bool bAtEarth = B && B->BodyId == FName(TEXT("earth"));
	if ((Flow == EOdysseySpaceFlow::Menu && MenuIndex == 0) || (Flow == EOdysseySpaceFlow::Navigation && bAtEarth))
	{
		DescendTime = 0.f;
		SetFlow(EOdysseySpaceFlow::Descending);
		Director->SetView(EOdysseyDirectorView::PlanetView);
	}
}

void AOdysseySpacePlayerController::OdysseyTravel(int32 Index)
{
	if (Flow != EOdysseySpaceFlow::Navigation)
	{
		EnterNavigation();
	}
	SelectedBody = Index;
	Confirm();
}

void AOdysseySpacePlayerController::HandleArrived(int32 BodyIndex)
{
	if (Director && Director->NumBodies() > 0)
	{
		SelectedBody = (BodyIndex + 1) % Director->NumBodies();
	}
}

void AOdysseySpacePlayerController::LogPerf(const FString& Tag) const
{
	const double GpuMs = FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles(0));
	const FPlatformMemoryStats Mem = FPlatformMemory::GetStats();
	UE_LOG(LogOdysseySpace, Log, TEXT("perf %s: frame %.2f ms, gpu %.2f ms, process memory %.0f MB, quality %s"),
		*Tag, FApp::GetDeltaTime() * 1000.0, GpuMs, Mem.UsedPhysical / (1024.0 * 1024.0), *GetQualityName());
}

void AOdysseySpacePlayerController::CycleQuality()
{
	if (UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		const int32 Level = (S->GetOverallScalabilityLevel() + 1 + 4) % 4;
		S->SetOverallScalabilityLevel(Level);
		S->ApplySettings(false);
		S->SaveSettings();
		UE_LOG(LogOdysseySpace, Log, TEXT("quality -> %s"), *GetQualityName());
	}
}

FString AOdysseySpacePlayerController::GetQualityName() const
{
	const UGameUserSettings* S = GEngine ? GEngine->GetGameUserSettings() : nullptr;
	const int32 L = S ? S->GetOverallScalabilityLevel() : -1;
	switch (L)
	{
	case 0: return TEXT("LOW");
	case 1: return TEXT("MEDIUM");
	case 2: return TEXT("HIGH");
	case 3: return TEXT("EPIC");
	default: return TEXT("CUSTOM");
	}
}

void AOdysseySpacePlayerController::BuildCaptureTour()
{
	auto After = [this](float Seconds) { return [this, Seconds]() { return StepClock >= Seconds; }; };
	auto Nothing = []() {};
	auto Progress = [this](float U) { return [this, U]() { return Director && Director->IsTraveling() && Director->GetTelemetry().Progress >= U; }; };
	auto Arrived = [this](float Seconds) { return [this, Seconds]() { return Director && !Director->IsTraveling() && Director->GetTelemetry().Phase == EOdysseyTransitPhase::Parked && Director->SinceArrival() >= Seconds; }; };

	Capture.Add({[this]() { return !bAwaitingShaders || ShaderWait > 3.f; }, Nothing, TEXT("SPACE_00_preparation")});
	Capture.Add({[this]() { return Logo && Logo->GetElapsed() >= 2.15f; }, Nothing, TEXT("SPACE_01_logo_draw_on")});
	Capture.Add({[this]() { return Logo && Logo->GetElapsed() >= 4.6f; }, Nothing, TEXT("SPACE_02_logo_lockup")});
	Capture.Add({[this]() { return Flow == EOdysseySpaceFlow::Menu && FlowTime >= 3.5f; }, Nothing, TEXT("SPACE_03_menu_earth")});
	Capture.Add({After(0.5f), [this]() { MenuIndex = 1; Confirm(); }, FString()});
	Capture.Add({After(4.5f), Nothing, TEXT("SPACE_04_earth_orbit_vista")});
	Capture.Add({After(0.2f), [this]() { CycleCamera(); }, FString()});
	Capture.Add({After(4.5f), Nothing, TEXT("SPACE_05_earth_planet_view")});
	Capture.Add({After(0.2f), [this]() { CycleCamera(); SelectBody(1); }, FString()});
	Capture.Add({After(3.5f), [this]() { Confirm(); }, FString()});
	Capture.Add({Progress(0.10f), Nothing, TEXT("SPACE_06_departure_burn_earth")});
	Capture.Add({Progress(0.46f), Nothing, TEXT("SPACE_07_cruise_toward_moon")});
	Capture.Add({Progress(0.715f), Nothing, TEXT("SPACE_08_flip_maneuver")});
	Capture.Add({Progress(0.90f), Nothing, TEXT("SPACE_09_arrival_burn_moon")});
	Capture.Add({Arrived(4.5f), Nothing, TEXT("SPACE_10_moon_orbit_vista")});
	Capture.Add({After(0.2f), [this]() { CycleCamera(); }, FString()});
	Capture.Add({After(4.5f), Nothing, TEXT("SPACE_11_moon_planet_view")});
	Capture.Add({After(0.2f), [this]() { CycleCamera(); SelectBody(2); }, FString()});
	Capture.Add({After(2.5f), [this]() { Confirm(); }, FString()});
	Capture.Add({Progress(0.35f), Nothing, TEXT("SPACE_12_cruise_toward_mars")});
	Capture.Add({Progress(0.93f), Nothing, TEXT("SPACE_13_arrival_burn_mars")});
	Capture.Add({Arrived(4.5f), Nothing, TEXT("SPACE_14_mars_orbit_vista")});
	Capture.Add({After(0.2f), [this]() { CycleCamera(); }, FString()});
	Capture.Add({After(4.5f), Nothing, TEXT("SPACE_15_mars_planet_view")});
	Capture.Add({After(2.0f), [this]() {
		UE_LOG(LogOdysseySpace, Log, TEXT("capture tour complete (%.1f s)"), CaptureClock);
		ConsoleCommand(TEXT("StopFPSChart"));
		UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
	}, FString()});
}

void AOdysseySpacePlayerController::TickCapture(float Dt)
{
	CaptureClock += Dt;
	StepClock += Dt;
	if (!Capture.IsValidIndex(CaptureStep))
	{
		return;
	}
	FCaptureStep& S = Capture[CaptureStep];
	if (S.Ready && !S.Ready())
	{
		if (CaptureClock > 600.f)
		{
			UE_LOG(LogOdysseySpace, Error, TEXT("capture tour timed out at step %d"), CaptureStep);
			UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
			Capture.Reset();
		}
		return;
	}
	if (S.Act)
	{
		S.Act();
	}
	if (CaptureStep == 0)
	{
		ConsoleCommand(TEXT("StartFPSChart"));
	}
	if (!S.Shot.IsEmpty())
	{
		LogPerf(S.Shot);
		const FString File = CaptureDir / (S.Shot + TEXT(".png"));
		FScreenshotRequest::RequestScreenshot(File, true, false);
		UE_LOG(LogOdysseySpace, Log, TEXT("capture %s (flow %s, t=%.1f)"), *File, *UEnum::GetValueAsString(Flow), CaptureClock);
	}
	++CaptureStep;
	StepClock = 0.f;
}
