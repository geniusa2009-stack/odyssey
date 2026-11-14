// Space experience verification (Unreal automation; no backend needed).
//
//   UnrealEditor Odyssey.uproject /Game/Space/Maps/L_Odyssey_SolarTransit -game -nullrhi -unattended -nosound
//       -ExecCmds="Automation RunTests Odyssey.Space.Flow" -TestExit="Automation Test Queue Empty"
//
// Checks the solar-transit map content (Earth, Moon, Mars with meshes, materials and sane scale;
// the transit vehicle with hull + plume; sky and sun kept on the camera), then drives the flow:
// intro logo -> skip -> menu -> Solar Transit -> Earth->Moon transfer -> Moon->Mars transfer.
// During each transfer it verifies phase order (aligning, departure burn, coast, flip, arrival
// burn), monotonic distance-to-go, velocity in range, that the vehicle never enters a body and that
// it ends in the target's parking orbit. Time dilation (x3) shortens the run; nothing is skipped.
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Components/StaticMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "OdysseyCelestialBody.h"
#include "OdysseyLogoWidget.h"
#include "OdysseySpaceGameMode.h"
#include "OdysseyTransitDirector.h"
#include "OdysseyTransitVehicle.h"
#include "Tests/AutomationCommon.h"

namespace OdysseySpaceFlow
{
static UWorld* GameWorld()
{
	for (const FWorldContext& C : GEngine->GetWorldContexts())
	{
		if ((C.WorldType == EWorldType::Game || C.WorldType == EWorldType::PIE) && C.World()) return C.World();
	}
	return nullptr;
}

enum class EStep { Boot, Static, Intro, Menu, Navigation, LaunchMoon, TravelMoon, ArrivedMoon, LaunchMars, TravelMars, ArrivedMars, Done };

struct FRun
{
	FAutomationTestBase* Test = nullptr;
	EStep Step = EStep::Boot;
	double StepStart = 0.0;
	TWeakObjectPtr<UWorld> World;
	TWeakObjectPtr<AOdysseySpacePlayerController> PC;
	TWeakObjectPtr<AOdysseyTransitDirector> Dir;
	TSet<EOdysseyTransitPhase> SeenPhases;
	TArray<EOdysseyTransitPhase> PhaseOrder;
	double LastDistance = TNumericLimits<double>::Max();
	double MaxVelocity = 0.0;
	bool bInsideBody = false;
	bool bDistanceMonotonic = true;

	static double Now() { return FPlatformTime::Seconds(); }
	double Elapsed() const { return Now() - StepStart; }
	void Go(EStep S) { Step = S; StepStart = Now(); }
	bool Fail(const FString& Why) { Test->AddError(Why); Go(EStep::Done); return true; }

	void Sample()
	{
		AOdysseyTransitDirector* D = Dir.Get();
		if (!D) return;
		const FOdysseyTransitTelemetry& T = D->GetTelemetry();
		if (PhaseOrder.Num() == 0 || PhaseOrder.Last() != T.Phase) PhaseOrder.Add(T.Phase);
		SeenPhases.Add(T.Phase);
		if (D->IsTraveling())
		{
			if (T.DistanceRemainingKm > LastDistance + 1.0) bDistanceMonotonic = false;
			LastDistance = T.DistanceRemainingKm;
			MaxVelocity = FMath::Max(MaxVelocity, T.VelocityKms);
		}
		if (const AOdysseyTransitVehicle* V = D->Vehicle)
		{
			for (const AOdysseyCelestialBody* B : D->Bodies)
			{
				if (B && FVector::Dist(V->GetActorLocation(), B->GetActorLocation()) < B->Radius * 1.005) bInsideBody = true;
			}
		}
	}

	void ResetLeg()
	{
		SeenPhases.Reset();
		PhaseOrder.Reset();
		LastDistance = TNumericLimits<double>::Max();
		MaxVelocity = 0.0;
		bDistanceMonotonic = true;
	}

	bool CheckLeg(int32 Target, double MinPeak)
	{
		AOdysseyTransitDirector* D = Dir.Get();
		const AOdysseyCelestialBody* B = D ? D->GetBody(Target) : nullptr;
		if (!B) return Fail(TEXT("target body missing after transfer"));
		Test->TestEqual(TEXT("current body after arrival"), D->GetCurrentBody(), Target);
		for (EOdysseyTransitPhase P : {EOdysseyTransitPhase::Aligning, EOdysseyTransitPhase::DepartureBurn, EOdysseyTransitPhase::Coast,
			 EOdysseyTransitPhase::FlipManeuver, EOdysseyTransitPhase::ArrivalBurn, EOdysseyTransitPhase::Parked})
		{
			Test->TestTrue(FString::Printf(TEXT("phase %s observed"), *UEnum::GetValueAsString(P)), SeenPhases.Contains(P));
		}
		// burns happen in order: departure before coast before flip before arrival burn
		auto Index = [this](EOdysseyTransitPhase P) { return PhaseOrder.IndexOfByKey(P); };
		Test->TestTrue(TEXT("phase order departure < coast < flip < arrival"),
			Index(EOdysseyTransitPhase::DepartureBurn) < Index(EOdysseyTransitPhase::Coast) &&
			Index(EOdysseyTransitPhase::Coast) < Index(EOdysseyTransitPhase::FlipManeuver) &&
			Index(EOdysseyTransitPhase::FlipManeuver) < Index(EOdysseyTransitPhase::ArrivalBurn));
		Test->TestTrue(TEXT("distance to go decreases monotonically"), bDistanceMonotonic);
		Test->TestTrue(FString::Printf(TEXT("peak velocity %.1f km/s >= %.1f"), MaxVelocity, MinPeak), MaxVelocity >= MinPeak);
		Test->TestFalse(TEXT("vehicle never entered a body"), bInsideBody);
		const double R = FVector::Dist(D->Vehicle->GetActorLocation(), B->GetActorLocation());
		Test->AddInfo(FString::Printf(TEXT("arrived at %s: vehicle at %.3f radii (parking orbit %.3f)"), *B->DisplayName.ToString(), R / B->Radius, B->OrbitFactor));
		Test->TestTrue(TEXT("vehicle in the target's parking orbit"), FMath::Abs(R / B->GetOrbitRadius() - 1.0) < 0.02);
		return false;
	}

	bool Tick()
	{
		if (Step != EStep::Boot && Step != EStep::Done) Sample();
		switch (Step)
		{
		case EStep::Boot:
		{
			UWorld* W = GameWorld();
			AOdysseySpacePlayerController* P = W ? Cast<AOdysseySpacePlayerController>(W->GetFirstPlayerController()) : nullptr;
			if (W && P && P->GetDirector() && W->GetMapName().Contains(TEXT("L_Odyssey_SolarTransit")))
			{
				World = W;
				PC = P;
				Dir = P->GetDirector();
				Go(EStep::Static);
			}
			else if (Elapsed() > 60.0)
			{
				return Fail(TEXT("L_Odyssey_SolarTransit did not load with an AOdysseySpacePlayerController and a transit director"));
			}
			return false;
		}
		case EStep::Static:
		{
			AOdysseyTransitDirector* D = Dir.Get();
			Test->TestEqual(TEXT("three destinations"), D->NumBodies(), 3);
			const TCHAR* Ids[] = {TEXT("earth"), TEXT("moon"), TEXT("mars")};
			for (int32 i = 0; i < D->NumBodies() && i < 3; ++i)
			{
				const AOdysseyCelestialBody* B = D->GetBody(i);
				Test->TestTrue(FString::Printf(TEXT("body %d id is %s"), i, Ids[i]), B->BodyId == FName(Ids[i]));
				Test->TestNotNull(FString::Printf(TEXT("%s surface mesh"), Ids[i]), B->Surface->GetStaticMesh().Get());
				Test->TestTrue(FString::Printf(TEXT("%s surface material"), Ids[i]), B->Surface->GetNumMaterials() > 0 && B->Surface->GetMaterial(0) != nullptr);
				Test->TestTrue(FString::Printf(TEXT("%s scale matches radius"), Ids[i]),
					FMath::IsNearlyEqual(B->Surface->GetComponentScale().X * B->MeshRadius, B->Radius, B->Radius * 0.001));
			}
			Test->TestTrue(TEXT("Earth has an atmosphere shell"), D->GetBody(0)->Atmosphere->GetStaticMesh() != nullptr);
			Test->TestTrue(TEXT("Mars has an atmosphere shell"), D->GetBody(2)->Atmosphere->GetStaticMesh() != nullptr);
			Test->TestTrue(TEXT("Moon is smaller than Earth, Mars between"), D->GetBody(1)->Radius < D->GetBody(2)->Radius && D->GetBody(2)->Radius < D->GetBody(0)->Radius);
			const AOdysseyTransitVehicle* V = D->Vehicle;
			Test->TestNotNull(TEXT("transit vehicle"), V);
			if (V)
			{
				Test->TestNotNull(TEXT("vehicle hull mesh"), V->Hull->GetStaticMesh().Get());
				Test->TestNotNull(TEXT("vehicle plume mesh"), V->Plume->GetStaticMesh().Get());
				const double Orbit = FVector::Dist(V->GetActorLocation(), D->GetBody(0)->GetActorLocation()) / D->GetBody(0)->GetOrbitRadius();
				Test->TestTrue(FString::Printf(TEXT("vehicle starts in Earth parking orbit (%.3f)"), Orbit), FMath::Abs(Orbit - 1.0) < 0.01);
			}
			Test->TestNotNull(TEXT("sky actor"), D->SkyActor.Get());
			Test->TestNotNull(TEXT("sun disc actor"), D->SunDiscActor.Get());
			Test->TestNotNull(TEXT("logo widget"), PC->GetLogo());
			UGameplayStatics::SetGlobalTimeDilation(World.Get(), 3.f);
			Go(EStep::Intro);
			return false;
		}
		case EStep::Intro:
			Test->TestTrue(TEXT("flow starts in the intro"), PC->GetFlow() == EOdysseySpaceFlow::Intro);
			Test->TestTrue(TEXT("logo intro playing"), PC->GetLogo() && PC->GetLogo()->GetElapsed() > 0.f);
			PC->SkipIntro();
			Go(EStep::Menu);
			return false;
		case EStep::Menu:
			if (PC->GetFlow() == EOdysseySpaceFlow::Menu)
			{
				Test->TestTrue(TEXT("menu camera"), Dir->GetView() == EOdysseyDirectorView::Menu);
				PC->MenuMove(1);
				Test->TestEqual(TEXT("menu item 2 selected"), PC->GetMenuIndex(), 1);
				PC->Confirm();
				Go(EStep::Navigation);
			}
			else if (Elapsed() > 15.0)
			{
				return Fail(TEXT("intro skip did not reach the menu"));
			}
			return false;
		case EStep::Navigation:
			Test->TestTrue(TEXT("Solar Transit opens navigation"), PC->GetFlow() == EOdysseySpaceFlow::Navigation);
			Test->TestTrue(TEXT("orbit vista camera"), Dir->GetView() == EOdysseyDirectorView::OrbitVista);
			PC->SelectBody(1);
			ResetLeg();
			PC->Confirm();
			Go(EStep::TravelMoon);
			return false;
		case EStep::TravelMoon:
			if (!Dir->IsTraveling() && Dir->GetTelemetry().Phase == EOdysseyTransitPhase::Parked && Dir->GetCurrentBody() == 1)
			{
				Go(EStep::ArrivedMoon);
			}
			else if (Elapsed() > 90.0)
			{
				return Fail(TEXT("Earth -> Moon transfer did not complete"));
			}
			return false;
		case EStep::ArrivedMoon:
			if (Elapsed() < 1.0) return false;
			CheckLeg(1, 9.0);
			PC->SelectBody(2);
			ResetLeg();
			PC->Confirm();
			Go(EStep::TravelMars);
			return false;
		case EStep::TravelMars:
			if (!Dir->IsTraveling() && Dir->GetTelemetry().Phase == EOdysseyTransitPhase::Parked && Dir->GetCurrentBody() == 2)
			{
				Go(EStep::ArrivedMars);
			}
			else if (Elapsed() > 120.0)
			{
				return Fail(TEXT("Moon -> Mars transfer did not complete"));
			}
			return false;
		case EStep::ArrivedMars:
			if (Elapsed() < 1.0) return false;
			CheckLeg(2, 30.0);
			UGameplayStatics::SetGlobalTimeDilation(World.Get(), 1.f);
			Go(EStep::Done);
			return false;
		case EStep::LaunchMoon:
		case EStep::LaunchMars:
		case EStep::Done:
			return true;
		}
		return true;
	}
};
}  // namespace OdysseySpaceFlow

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOdysseySpaceFlowTest, "Odyssey.Space.Flow",
	EAutomationTestFlags::ClientContext | EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FOdysseySpaceFlowTest::RunTest(const FString& Parameters)
{
	using namespace OdysseySpaceFlow;
	TSharedRef<FRun> Run = MakeShared<FRun>();
	Run->Test = this;
	Run->StepStart = FRun::Now();
	ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([Run]() { return Run->Tick(); }));
	return true;
}

#endif  // WITH_DEV_AUTOMATION_TESTS
