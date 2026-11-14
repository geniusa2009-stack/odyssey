// Engineering slice verification (Unreal automation, needs the generated map and a running backend).
//
//   backend: development environment from Config/DefaultGame.ini (http://127.0.0.1:8000)
//   UnrealEditor Odyssey.uproject -game -nullrhi -unattended -nosound
//       -ExecCmds="Automation RunTests Odyssey.Slice.Engineering; Quit"
//
// Plays L_EarthCommand_Slice and checks, from the map definition
// (Content/Systems/Greybox/L_EarthCommand_Slice.layout.json):
//   * Engineering anchor/zone/console exist once, bound to their semantic ids, inside the room;
//   * Sys_PowerBusB is the AOdysseyPowerConsole proxy at true scale with box collision,
//     DIAGNOSTIC = system.inspect and BREAKER SERVICE = repair.perform;
//   * every proxy actor carries a SM_PROXY_ mesh at scale 1; bus_room lights are light fixtures;
//   * the player capsule walks corridor → Engineering → corridor → Engineering (CharacterMovement);
//   * the backend accepts the zone entry (semantic location = engineering);
//   * lights at full output and the warning off before the incident; once the backend's power
//     incident involves bus B the room lights follow the bus_room rule and the warning comes on;
//   * console presses go through SubmitIntent and resolve as system.inspect / repair.perform;
//   * after the backend resolves the incident, the lights return to full and the warning goes off.
// It never decides an outcome: every expected value is computed from the backend's reported state.
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "CollisionQueryParams.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/LightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyLightFixture.h"
#include "OdysseyObjectPresentationComponent.h"
#include "OdysseyPowerConsole.h"
#include "OdysseySemanticAnchor.h"
#include "OdysseySemanticBindingComponent.h"
#include "OdysseySemanticZone.h"
#include "OdysseySliceTestProbe.h"
#include "PhysicsEngine/BodySetup.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace OdysseyEngineeringSlice
{
static const FName Engineering(TEXT("earth.command.engineering"));
static const FName Bus(TEXT("earth.command.engineering.power_bus_b"));

struct FRoom
{
	double X0 = 0, X1 = 0, Y0 = 0, Y1 = 0, H = 0;
	double DoorX = 0, DoorY = 0;
	TMap<FString, TMap<FString, double>> BusRoomRule;  // power/status/mode -> value -> scale
	TArray<TPair<FVector, double>> Lights;              // authored Engineering light positions and intensities

	// Authored intensity of the light placed at P (the presentation rescales lights at runtime).
	double AuthoredIntensity(const FVector& P) const
	{
		for (const TPair<FVector, double>& L : Lights)
		{
			if (FVector::Dist(L.Key, P) < 2.0) return L.Value;
		}
		return -1.0;
	}
};

static bool LoadRoom(FRoom& Out, FString& Error)
{
	FString Text;
	const FString Path = FPaths::ProjectContentDir() / TEXT("Systems/Greybox/L_EarthCommand_Slice.layout.json");
	TSharedPtr<FJsonObject> Root;
	if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root)
	{
		Error = TEXT("map definition unreadable");
		return false;
	}
	for (const TSharedPtr<FJsonValue>& V : Root->GetArrayField(TEXT("areas")))
	{
		const TSharedPtr<FJsonObject> A = V->AsObject();
		if (A->GetStringField(TEXT("id")) != TEXT("engineering")) continue;
		const TArray<TSharedPtr<FJsonValue>>& B = A->GetArrayField(TEXT("bounds"));
		Out.X0 = B[0]->AsNumber(); Out.X1 = B[1]->AsNumber(); Out.Y0 = B[2]->AsNumber(); Out.Y1 = B[3]->AsNumber();
		Out.H = A->GetNumberField(TEXT("height"));
		const TArray<TSharedPtr<FJsonValue>>& N = A->GetObjectField(TEXT("doors"))->GetArrayField(TEXT("N"));
		Out.DoorX = N[0]->AsArray()[0]->AsNumber();
		Out.DoorY = Out.Y1;
		for (const TSharedPtr<FJsonValue>& LV : A->GetArrayField(TEXT("lights")))
		{
			const TSharedPtr<FJsonObject> L = LV->AsObject();
			const TArray<TSharedPtr<FJsonValue>>& At = L->GetArrayField(TEXT("at"));
			Out.Lights.Emplace(FVector(At[0]->AsNumber(), At[1]->AsNumber(), At[2]->AsNumber()), L->GetNumberField(TEXT("intensity")));
		}
	}
	const TSharedPtr<FJsonObject> Rule = Root->GetObjectField(TEXT("light_rules"))->GetObjectField(TEXT("bus_room"));
	for (const TCHAR* Field : {TEXT("power"), TEXT("mode"), TEXT("status")})
	{
		if (Rule->HasField(Field))
		{
			for (const auto& P : Rule->GetObjectField(Field)->Values)
			{
				Out.BusRoomRule.FindOrAdd(Field).Add(FString(*P.Key), P.Value->AsNumber());
			}
		}
	}
	return Out.X1 > Out.X0;
}

static double ExpectedBusRoom(const FRoom& R, const FOdysseyObjectView& V)
{
	double S = 1.0;
	auto Mul = [&](const TCHAR* Field, FName Value) {
		if (const TMap<FString, double>* M = R.BusRoomRule.Find(Field))
		{
			if (const double* F = M->Find(Value.ToString())) S *= *F;
		}
	};
	Mul(TEXT("power"), V.Power);
	Mul(TEXT("mode"), V.Mode);
	Mul(TEXT("status"), V.Status);
	return S;
}

static UWorld* GameWorld()
{
	for (const FWorldContext& C : GEngine->GetWorldContexts())
	{
		if ((C.WorldType == EWorldType::Game || C.WorldType == EWorldType::PIE) && C.World()) return C.World();
	}
	return nullptr;
}

enum class EPhase
{
	Boot, Static, Ready, Settle, WalkIn, Zone, WalkOut, WalkBack, PreIncident, WaitIncident, IncidentLights,
	PressDiagnostic, WaitDiagnostic, PressRepair, WaitRepair, ClockAccelerated, WaitClock, WaitResolved, ResolvedLights, Done
};

struct FRun
{
	FAutomationTestBase* Test = nullptr;
	FRoom Room;
	EPhase Phase = EPhase::Boot;
	double PhaseStart = 0.0;
	TWeakObjectPtr<UWorld> World;
	TWeakObjectPtr<ACharacter> Pawn;
	TWeakObjectPtr<AOdysseyPowerConsole> Console;
	TWeakObjectPtr<UOdysseyObjectPresentationComponent> Presentation;
	TArray<TWeakObjectPtr<AOdysseyLightFixture>> Fixtures;
	TArray<float> FixtureBase;
	TWeakObjectPtr<ULightComponent> Warning;
	float WarningBase = 0.f;
	TStrongObjectPtr<UOdysseySliceTestProbe> Probe;
	int64 PendingId = 0;
	FName PendingAction;
	double Expected = 1.0;

	double Now() const { return FPlatformTime::Seconds(); }
	double Elapsed() const { return Now() - PhaseStart; }
	void Go(EPhase P) { Phase = P; PhaseStart = Now(); }
	bool Fail(const FString& Msg) { Test->AddError(Msg); Phase = EPhase::Done; return true; }
	void Info(const FString& Msg) { Test->AddInfo(Msg); UE_LOG(LogTemp, Display, TEXT("[OdysseySlice] %s"), *Msg); }
	UOdysseyBackendSubsystem* Backend() const { return World.IsValid() ? UOdysseyBackendSubsystem::Get(World.Get()) : nullptr; }

	bool Inside(const FVector& P, double Margin = 0) const
	{
		return P.X >= Room.X0 + Margin && P.X <= Room.X1 - Margin && P.Y >= Room.Y0 + Margin && P.Y <= Room.Y1 - Margin;
	}

	// Drives the pawn with movement input toward Target; true when within Tolerance.
	bool WalkTo(const FVector2D& Target, double Tolerance = 45.0)
	{
		ACharacter* C = Pawn.Get();
		const FVector2D At(C->GetActorLocation());
		const FVector2D D = Target - At;
		if (D.Size() <= Tolerance) return true;
		const FVector Dir(D.GetSafeNormal(), 0.0);
		C->SetActorRotation(Dir.Rotation());
		C->AddMovementInput(Dir, 1.f, true);
		return false;
	}

	bool ActiveIncidentOnBus() const
	{
		for (const FOdysseyIncidentView& I : Backend()->GetIncidents(true))
		{
			if (!I.bResolved && I.InvolvedObjects.Contains(Bus)) return true;
		}
		return false;
	}

	bool CheckLights(double BusScale, double WarnScale, const TCHAR* When)
	{
		bool Ok = true;
		const float G = Presentation->GetGroupScale(TEXT("bus_room"));
		const float W = Presentation->GetGroupScale(TEXT("warning"));
		Info(FString::Printf(TEXT("%s: bus_room scale %.3f (expected %.3f), warning scale %.3f (expected %.3f)"), When, G, BusScale, W, WarnScale));
		Ok &= Test->TestTrue(FString::Printf(TEXT("%s bus_room group scale follows power_bus_b"), When), FMath::IsNearlyEqual(G, BusScale, 0.01));
		Ok &= Test->TestTrue(FString::Printf(TEXT("%s warning group scale"), When), FMath::IsNearlyEqual(W, WarnScale, 0.01));
		for (int32 I = 0; I < Fixtures.Num(); ++I)
		{
			AOdysseyLightFixture* F = Fixtures[I].Get();
			const float Want = FixtureBase[I] * BusScale;
			Info(FString::Printf(TEXT("%s: %s intensity %.1f (expected %.1f), emissive factor %.3f"), When, *F->GetName(), F->Light->Intensity, Want, F->GetEmissiveFactor()));
			Ok &= Test->TestTrue(FString::Printf(TEXT("%s %s light intensity"), When, *F->GetName()), FMath::IsNearlyEqual(F->Light->Intensity, Want, FMath::Max(1.f, Want * 0.01f)));
			Ok &= Test->TestTrue(FString::Printf(TEXT("%s %s emissive follows light"), When, *F->GetName()), FMath::IsNearlyEqual(F->GetEmissiveFactor(), static_cast<float>(BusScale), 0.02f));
		}
		const float WantW = WarningBase * WarnScale;
		Info(FString::Printf(TEXT("%s: warning light intensity %.1f (expected %.1f)"), When, Warning->Intensity, WantW));
		Ok &= Test->TestTrue(FString::Printf(TEXT("%s warning light intensity"), When), FMath::IsNearlyEqual(Warning->Intensity, WantW, FMath::Max(1.f, WantW * 0.01f)));
		return Ok;
	}

	bool StaticChecks()
	{
		UWorld* W = World.Get();
		int32 Anchors = 0, Zones = 0, Consoles = 0;
		for (TActorIterator<AOdysseySemanticAnchor> It(W); It; ++It)
		{
			if (It->GetLocationId() != Engineering) continue;
			++Anchors;
			Test->TestTrue(TEXT("Engineering anchor inside the room"), Inside(It->GetActorLocation(), 20));
		}
		for (TActorIterator<AOdysseySemanticZone> It(W); It; ++It)
		{
			if (It->GetLocationId() != Engineering) continue;
			++Zones;
			const FBox B = It->Volume->Bounds.GetBox();
			Info(FString::Printf(TEXT("Zone_Engineering box %s"), *B.ToString()));
			Test->TestTrue(TEXT("Engineering zone inside the room"), Inside(B.Min, 0) && Inside(B.Max, 0) && B.Max.Z <= Room.H + 1);
		}
		for (TActorIterator<AOdysseyPowerConsole> It(W); It; ++It)
		{
			if (It->Binding->SemanticId == Bus) { ++Consoles; Console = *It; }
		}
		Test->TestEqual(TEXT("exactly one Engineering anchor"), Anchors, 1);
		Test->TestEqual(TEXT("exactly one Engineering zone"), Zones, 1);
		if (!Test->TestEqual(TEXT("exactly one console bound to power_bus_b"), Consoles, 1)) return false;

		AOdysseyPowerConsole* C = Console.Get();
#if WITH_EDITOR
		Test->TestEqual(TEXT("console actor label"), C->GetActorLabel(), FString(TEXT("Sys_PowerBusB")));
#endif
		Test->TestTrue(TEXT("console inside Engineering"), Inside(C->GetActorLocation(), 50));
		Test->TestEqual(TEXT("console has 2 controls"), C->Controls.Num(), 2);
		if (C->Controls.Num() == 2)
		{
			Test->TestEqual(TEXT("DIAGNOSTIC action"), C->Controls[0].Action, FName(TEXT("system.inspect")));
			Test->TestEqual(TEXT("DIAGNOSTIC label"), C->Controls[0].Label.ToString(), FString(TEXT("DIAGNOSTIC")));
			Test->TestEqual(TEXT("BREAKER SERVICE action"), C->Controls[1].Action, FName(TEXT("repair.perform")));
			Test->TestEqual(TEXT("BREAKER SERVICE label"), C->Controls[1].Label.ToString(), FString(TEXT("BREAKER SERVICE")));
		}
		UStaticMesh* M = C->Body->GetStaticMesh();
		if (Test->TestNotNull(TEXT("console proxy mesh"), M))
		{
			const FBox B = M->GetBoundingBox();
			Info(FString::Printf(TEXT("console mesh %s bounds %s"), *M->GetName(), *B.ToString()));
			Test->TestTrue(TEXT("console mesh is SM_PROXY_PowerConsole"), M->GetName() == TEXT("SM_PROXY_PowerConsole"));
			Test->TestTrue(TEXT("console envelope 90x180x125 cm, pivot bottom-centre"),
				B.GetSize().Equals(FVector(90, 180, 125), 2.0) && FMath::IsNearlyZero(B.Min.Z, 0.5) && FMath::Abs(B.GetCenter().Y) < 1.0);
			Test->TestTrue(TEXT("console simple box collision"), M->GetBodySetup() && M->GetBodySetup()->AggGeom.BoxElems.Num() == 1);
		}
		Test->TestTrue(TEXT("console actor not scaled"), C->GetActorScale3D().Equals(FVector::OneVector, 1e-3));
		Test->TestTrue(TEXT("console blocks the player"), C->Body->GetCollisionResponseToChannel(ECC_Pawn) == ECR_Block);

		Presentation = C->Presentation;
		for (const FOdysseyLightGroup& G : Presentation->LightGroups)
		{
			if (G.Name == TEXT("bus_room"))
			{
				for (AActor* A : G.LightActors)
				{
					AOdysseyLightFixture* F = Cast<AOdysseyLightFixture>(A);
					if (Test->TestNotNull(TEXT("bus_room light is a ceiling light fixture"), F))
					{
						Fixtures.Add(F);
						FixtureBase.Add(static_cast<float>(Room.AuthoredIntensity(F->GetActorLocation())));
						Test->TestTrue(TEXT("fixture matches an authored Engineering light"), FixtureBase.Last() > 0.f);
						const UStaticMesh* FixtureMesh = F->Fixture->GetStaticMesh();
						const bool IsStructuralFixture = FixtureMesh && FixtureMesh->GetName() == TEXT("SM_PROXY_CeilingLight_Linear");
						const bool IsProductionFixture = FixtureMesh && FixtureMesh->GetPathName() == TEXT("/Game/Earth/EarthCommand/Engineering/Production/Equipment/OD_ENV_CeilingLight/OD_ENV_CeilingLight.OD_ENV_CeilingLight");
						Test->TestTrue(TEXT("fixture uses the validated structural or ODYSSEY production mesh"), IsStructuralFixture || IsProductionFixture);
						if (IsProductionFixture)
						{
							const FBox FixtureBounds = FixtureMesh->GetBoundingBox();
							Test->TestTrue(TEXT("production fixture preserves its imported 200x50x14 cm envelope and top pivot"),
								FixtureBounds.GetSize().Equals(FVector(200, 50, 14), 2.0) && FMath::IsNearlyZero(FixtureBounds.Max.Z, 1.0));
						}
						Test->TestTrue(TEXT("ceiling fixture actor has unit scale"), F->GetActorScale3D().Equals(FVector::OneVector, 1e-3));
						Test->TestTrue(TEXT("fixture flush with the ceiling"), FMath::IsNearlyEqual(F->GetActorLocation().Z, Room.H, 1.0));
					}
				}
			}
			if (G.Name == TEXT("warning") && G.LightActors.Num() == 1 && G.LightActors[0])
			{
				Warning = G.LightActors[0]->FindComponentByClass<ULightComponent>();
				WarningBase = static_cast<float>(Room.AuthoredIntensity(G.LightActors[0]->GetActorLocation()));
				Test->TestTrue(TEXT("warning light matches the authored Engineering warning"), WarningBase > 0.f);
			}
		}
		Test->TestEqual(TEXT("bus_room fixtures"), Fixtures.Num(), 4);
		if (!Test->TestTrue(TEXT("warning light wired"), Warning.IsValid())) return false;

		int32 Proxies = 0;
		for (TActorIterator<AStaticMeshActor> It(W); It; ++It)
		{
			if (!It->ActorHasTag(TEXT("OdysseyProxy"))) continue;
			++Proxies;
			UStaticMesh* PM = It->GetStaticMeshComponent()->GetStaticMesh();
			Test->TestTrue(FString::Printf(TEXT("%s has a SM_PROXY_ mesh"), *It->GetName()), PM && PM->GetName().StartsWith(TEXT("SM_PROXY_")));
			Test->TestTrue(FString::Printf(TEXT("%s not scaled"), *It->GetName()), It->GetActorScale3D().Equals(FVector::OneVector, 1e-3));
			Test->TestTrue(FString::Printf(TEXT("%s inside Engineering"), *It->GetName()), Inside(It->GetActorLocation(), 0));
		}
		Info(FString::Printf(TEXT("Unreal-only proxy actors in Engineering: %d"), Proxies));
		Test->TestEqual(TEXT("proxy dressing actors"), Proxies, 7);

		// Capsule sweep corridor ↔ room through the door (static collision only).
		const float R = Pawn->GetCapsuleComponent()->GetScaledCapsuleRadius();
		const float HH = Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		FCollisionQueryParams Q(SCENE_QUERY_STAT(OdysseySliceSweep), false, Pawn.Get());
		const FVector A(Room.DoorX, Room.DoorY + 150, HH + 3), B(Room.DoorX, (Room.Y0 + Room.Y1) / 2, HH + 3);
		FHitResult Hit;
		const bool Blocked = W->SweepSingleByChannel(Hit, A, B, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(R, HH), Q);
		Test->TestFalse(FString::Printf(TEXT("capsule sweep corridor → Engineering clear (hit %s)"), Blocked ? *GetNameSafe(Hit.GetActor()) : TEXT("none")), Blocked);
		const bool BlockedBack = W->SweepSingleByChannel(Hit, B, A, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeCapsule(R, HH), Q);
		Test->TestFalse(TEXT("capsule sweep Engineering → corridor clear"), BlockedBack);
		return true;
	}

	bool Tick()
	{
		switch (Phase)
		{
		case EPhase::Boot:
		{
			UWorld* W = GameWorld();
			APlayerController* PC = W ? W->GetFirstPlayerController() : nullptr;
			ACharacter* C = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
			if (W && C && W->GetMapName().Contains(TEXT("L_EarthCommand_Slice")))
			{
				World = W;
				Pawn = C;
				Probe.Reset(NewObject<UOdysseySliceTestProbe>());
				Backend()->OnCommandResolved.AddDynamic(Probe.Get(), &UOdysseySliceTestProbe::HandleResolved);
				// a fresh campaign every run: the incident has to happen during this test
				Backend()->ForgetStoredSession();
				Backend()->StartSession();
				Go(EPhase::Static);
			}
			else if (Elapsed() > 120) return Fail(TEXT("map L_EarthCommand_Slice with a player pawn did not load"));
			return false;
		}
		case EPhase::Static:
			if (!StaticChecks()) return Fail(TEXT("static Engineering checks failed"));
			Go(EPhase::Ready);
			return false;
		case EPhase::Ready:
			if (Backend()->IsSessionReady()) { Go(EPhase::Settle); return false; }
			return Elapsed() > 60 ? Fail(TEXT("backend session not ready (is the backend running on 127.0.0.1:8000?)")) : false;
		case EPhase::Settle:
			if (Elapsed() < 1.0) return false;
			Info(FString::Printf(TEXT("session ready; backend location %s"), *Backend()->GetPlayerSemanticLocation().ToString()));
			Pawn->TeleportTo(FVector(Room.DoorX, Room.DoorY + 130, Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 5), FRotator(0, -90, 0));
			Go(EPhase::WalkIn);
			return false;
		case EPhase::WalkIn:
			if (WalkTo(FVector2D(Room.DoorX, (Room.Y0 + Room.Y1) / 2)))
			{
				Info(FString::Printf(TEXT("walked corridor → Engineering in %.1f s, at %s"), Elapsed(), *Pawn->GetActorLocation().ToString()));
				Test->TestTrue(TEXT("player inside Engineering"), Inside(Pawn->GetActorLocation(), 0));
				Go(EPhase::Zone);
			}
			return Elapsed() > 25 ? Fail(FString::Printf(TEXT("could not walk into Engineering (stuck at %s)"), *Pawn->GetActorLocation().ToString())) : false;
		case EPhase::Zone:
			if (Backend()->GetPlayerSemanticLocation() == Engineering)
			{
				Info(FString::Printf(TEXT("backend accepted world.zone_entered → %s after %.1f s"), *Engineering.ToString(), Elapsed()));
				Go(EPhase::WalkOut);
				return false;
			}
			return Elapsed() > 20 ? Fail(TEXT("backend location did not become engineering (Zone_Engineering)")) : false;
		case EPhase::WalkOut:
			if (WalkTo(FVector2D(Room.DoorX, Room.DoorY + 130)))
			{
				Info(FString::Printf(TEXT("walked Engineering → corridor in %.1f s, at %s"), Elapsed(), *Pawn->GetActorLocation().ToString()));
				Test->TestTrue(TEXT("player back in the corridor"), Pawn->GetActorLocation().Y > Room.Y1);
				Go(EPhase::WalkBack);
			}
			return Elapsed() > 25 ? Fail(TEXT("could not walk out of Engineering")) : false;
		case EPhase::WalkBack:
		{
			// operator position in front of the console
			const FVector CL = Console->GetActorLocation();
			const FVector Front = Console->GetActorForwardVector();
			const FVector2D Op(CL + Front * 115.0);
			if (Pawn->GetActorLocation().Y > Room.DoorY - 120)
			{
				WalkTo(FVector2D(Room.DoorX, Room.DoorY - 150), 20);  // back through the door first
			}
			else if (WalkTo(Op, 30))
			{
				Info(FString::Printf(TEXT("at the Power Console operator position %s after %.1f s"), *Pawn->GetActorLocation().ToString(), Elapsed()));
				Go(EPhase::PreIncident);
			}
			return Elapsed() > 30 ? Fail(TEXT("could not reach the Power Console")) : false;
		}
		case EPhase::PreIncident:
		{
			if (Elapsed() < 1.0) return false;  // presentation blend
			const FOdysseyObjectView V = Backend()->GetObjectView(Bus);
			Test->TestTrue(TEXT("backend reveals power_bus_b"), V.bFound);
			Info(FString::Printf(TEXT("power_bus_b before incident: power=%s mode=%s status=%s"), *V.Power.ToString(), *V.Mode.ToString(), *V.Status.ToString()));
			if (!ActiveIncidentOnBus())
			{
				CheckLights(ExpectedBusRoom(Room, V), 0.0, TEXT("before incident"));
			}
			Go(EPhase::WaitIncident);
			return false;
		}
		case EPhase::WaitIncident:
			if (ActiveIncidentOnBus())
			{
				Info(FString::Printf(TEXT("backend incident involving power_bus_b after %.1f s"), Elapsed()));
				Go(EPhase::IncidentLights);
				return false;
			}
			return Elapsed() > 150 ? Fail(TEXT("no backend incident involving power_bus_b within 150 s")) : false;
		case EPhase::IncidentLights:
		{
			if (Elapsed() < 1.5) return false;
			const FOdysseyObjectView V = Backend()->GetObjectView(Bus);
			Expected = ExpectedBusRoom(Room, V);
			Info(FString::Printf(TEXT("power_bus_b during incident: power=%s mode=%s status=%s"), *V.Power.ToString(), *V.Mode.ToString(), *V.Status.ToString()));
			CheckLights(Expected, 1.0, TEXT("during incident"));
			Go(EPhase::PressDiagnostic);
			return false;
		}
		case EPhase::PressDiagnostic:
		case EPhase::PressRepair:
		{
			const int32 Index = Phase == EPhase::PressDiagnostic ? 0 : 1;
			Console->SetPanelActive(true);
			Test->TestTrue(TEXT("panel active"), Console->IsPanelActive());
			for (const FOdysseyConsoleControlState& S : Console->GetControlStates())
			{
				Info(FString::Printf(TEXT("control %s (%s): offered=%d available=%d reason=%s"), *S.Control.Label.ToString(), *S.Control.Action.ToString(), S.bOffered, S.bAvailable, *S.Reason.ToString()));
			}
			PendingAction = Console->Controls[Index].Action;
			PendingId = Console->PressControl(Index);
			Info(FString::Printf(TEXT("pressed %s → SubmitIntent local id %lld"), *Console->Controls[Index].Label.ToString(), PendingId));
			if (!Test->TestTrue(TEXT("PressControl reached SubmitIntent"), PendingId != 0)) return Fail(TEXT("console press was not submitted"));
			Go(Index == 0 ? EPhase::WaitDiagnostic : EPhase::WaitRepair);
			return false;
		}
		case EPhase::WaitDiagnostic:
		case EPhase::WaitRepair:
		{
			const FOdysseyCommandResolution* R = Probe->Find(PendingId);
			if (R && R->Outcome == TEXT("stale"))
			{
				R = Probe->Resolutions.FindByPredicate([this](const FOdysseyCommandResolution& X) { return X.LocalId != PendingId && X.Action == PendingAction && X.Outcome != TEXT("stale"); });
			}
			if (R)
			{
				Info(FString::Printf(TEXT("resolution: action=%s target=%s outcome=%s reason=%s error=%s"), *R->Action.ToString(), *R->Target.ToString(), *R->Outcome.ToString(), *R->Reason.ToString(), *R->ErrorCode.ToString()));
				Test->TestEqual(TEXT("resolved action"), R->Action, PendingAction);
				Test->TestEqual(TEXT("resolved target"), R->Target, Bus);
				Test->TestEqual(TEXT("backend applied the action"), R->Outcome, FName(TEXT("applied")));
				Go(Phase == EPhase::WaitDiagnostic ? EPhase::PressRepair : EPhase::ClockAccelerated);
				return false;
			}
			return Elapsed() > 30 ? Fail(FString::Printf(TEXT("no resolution for %s"), *PendingAction.ToString())) : false;
		}
		case EPhase::ClockAccelerated:
		{
			// Last step of the backend's repair_at_once strategy (Tests/Data/earth_command_power_incident_strategies.json):
			// the player lets trusted time run faster so the repair completes. Not a console control.
			FOdysseySemanticIntent Clock;
			Clock.Action = TEXT("mission.clock_set");
			FOdysseyIntentParam Mode;
			Mode.Name = TEXT("mode");
			Mode.StringValue = TEXT("ACCELERATED");
			Clock.Params.Add(Mode);
			PendingAction = Clock.Action;
			PendingId = Backend()->SubmitIntent(Clock);
			Info(FString::Printf(TEXT("mission.clock_set mode=ACCELERATED → SubmitIntent local id %lld"), PendingId));
			Go(EPhase::WaitClock);
			return false;
		}
		case EPhase::WaitClock:
		{
			if (const FOdysseyCommandResolution* R = Probe->Find(PendingId))
			{
				Info(FString::Printf(TEXT("resolution: action=%s outcome=%s reason=%s"), *R->Action.ToString(), *R->Outcome.ToString(), *R->Reason.ToString()));
				Test->TestEqual(TEXT("clock set applied"), R->Outcome, FName(TEXT("applied")));
				Go(EPhase::WaitResolved);
				return false;
			}
			return Elapsed() > 30 ? Fail(TEXT("no resolution for mission.clock_set")) : false;
		}
		case EPhase::WaitResolved:
			if (!ActiveIncidentOnBus())
			{
				Info(FString::Printf(TEXT("backend resolved the incident after %.1f s"), Elapsed()));
				Go(EPhase::ResolvedLights);
				return false;
			}
			return Elapsed() > 180 ? Fail(TEXT("incident not resolved within 180 s after the repair")) : false;
		case EPhase::ResolvedLights:
		{
			if (Elapsed() < 1.5) return false;
			const FOdysseyObjectView V = Backend()->GetObjectView(Bus);
			Info(FString::Printf(TEXT("power_bus_b after repair: power=%s mode=%s status=%s"), *V.Power.ToString(), *V.Mode.ToString(), *V.Status.ToString()));
			CheckLights(ExpectedBusRoom(Room, V), 0.0, TEXT("after resolution"));
			Test->TestTrue(TEXT("room lights restored to full output"), FMath::IsNearlyEqual(ExpectedBusRoom(Room, V), 1.0, 1e-3));
			Go(EPhase::Done);
			return true;
		}
		case EPhase::Done:
			return true;
		}
		return true;
	}
};
}  // namespace OdysseyEngineeringSlice

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOdysseyEngineeringSliceTest, "Odyssey.Slice.Engineering",
	EAutomationTestFlags::ClientContext | EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FOdysseyEngineeringSliceTest::RunTest(const FString& Parameters)
{
	using namespace OdysseyEngineeringSlice;
	TSharedRef<FRun> Run = MakeShared<FRun>();
	Run->Test = this;
	FString Error;
	if (!TestTrue(TEXT("Engineering in the map definition"), LoadRoom(Run->Room, Error)))
	{
		AddError(Error);
		return false;
	}
	Run->PhaseStart = Run->Now();
	ADD_LATENT_AUTOMATION_COMMAND(FFunctionLatentCommand([Run]() { return Run->Tick(); }));
	return true;
}

#endif  // WITH_DEV_AUTOMATION_TESTS
