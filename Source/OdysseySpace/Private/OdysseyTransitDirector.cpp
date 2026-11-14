#include "OdysseyTransitDirector.h"

#include "Camera/CameraComponent.h"
#include "Engine/DirectionalLight.h"
#include "EngineUtils.h"
#include "OdysseyCelestialBody.h"
#include "OdysseySpace.h"
#include "OdysseyTransitVehicle.h"

namespace
{
	constexpr double AccelFraction = 0.20;
	constexpr double DecelFraction = 0.24;
	constexpr double BaseSpeed = 0.12;      // fraction of cruise speed at both ends of a transfer
	constexpr double FlipStart = 1.0 - DecelFraction - 0.085;
	constexpr double FlipEnd = 1.0 - DecelFraction - 0.006;
	constexpr int32 ArcSamples = 256;

	double Smooth(double A, double B, double X)
	{
		const double T = FMath::Clamp((X - A) / (B - A), 0.0, 1.0);
		return T * T * (3.0 - 2.0 * T);
	}

	double Smoother(double X)
	{
		X = FMath::Clamp(X, 0.0, 1.0);
		return X * X * X * (X * (X * 6.0 - 15.0) + 10.0);
	}

	// integral of smoothstep from 0 to X
	double RampArea(double X) { return X * X * X - 0.5 * X * X * X * X; }

	FQuat LookQuat(const FVector& From, const FVector& To, const FVector& Up)
	{
		const FVector F = (To - From).GetSafeNormal();
		return FRotationMatrix::MakeFromXZ(F.IsNearlyZero() ? FVector::ForwardVector : F, Up).ToQuat();
	}

	FTransform Blend(const FTransform& A, const FTransform& B, double Alpha)
	{
		return FTransform(FQuat::Slerp(A.GetRotation(), B.GetRotation(), Alpha), FMath::Lerp(A.GetLocation(), B.GetLocation(), Alpha));
	}

	FVector SunDirection(const UWorld* World)
	{
		if (TActorIterator<ADirectionalLight> It(World); It)
		{
			return -It->GetActorForwardVector();
		}
		return FVector(-0.6, 0.7, 0.25).GetSafeNormal();
	}
}

AOdysseyTransitDirector::AOdysseyTransitDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostPhysics;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(RootComponent);
	Camera->SetFieldOfView(55.f);
	Camera->bConstrainAspectRatio = false;
	Camera->SetUsingAbsoluteLocation(true);
	Camera->SetUsingAbsoluteRotation(true);
}

AOdysseyCelestialBody* AOdysseyTransitDirector::GetBody(int32 Index) const
{
	return Bodies.IsValidIndex(Index) ? Bodies[Index].Get() : nullptr;
}

void AOdysseyTransitDirector::BeginPlay()
{
	Super::BeginPlay();
	Bodies.RemoveAll([](const TObjectPtr<AOdysseyCelestialBody>& B) { return B == nullptr; });
	Current = Bodies.IsValidIndex(StartBody) ? StartBody : 0;
	Target = Current;
	OrbitTheta = 0.9;
	if (AOdysseyCelestialBody* B = GetBody(Current); B && Vehicle)
	{
		// start on the day side, a little ahead of the sun-facing point
		OrbitTheta = B->OrbitAngleToward(SunDirection(GetWorld())) - 0.5;
		Vehicle->SetActorLocation(B->OrbitPoint(OrbitTheta));
		VehicleQuat = FRotationMatrix::MakeFromXZ(B->OrbitTangent(OrbitTheta), (Vehicle->GetActorLocation() - B->GetActorLocation()).GetSafeNormal()).ToQuat();
		Vehicle->SetActorRotation(VehicleQuat);
	}
	Telemetry.Origin = Telemetry.Target = Current;
	UpdateCamera(0.f);
	UE_LOG(LogOdysseySpace, Log, TEXT("transit director ready: %d bodies, vehicle %s, start %d"), Bodies.Num(), Vehicle ? *Vehicle->GetName() : TEXT("none"), Current);
}

bool AOdysseyTransitDirector::LegIsLong(int32 A, int32 B) const
{
	const AOdysseyCelestialBody* BA = GetBody(A);
	const AOdysseyCelestialBody* BB = GetBody(B);
	return (BA && BA->BodyId == FName(TEXT("mars"))) || (BB && BB->BodyId == FName(TEXT("mars")));
}

double AOdysseyTransitDirector::RealDistanceKm(int32 A, int32 B) const
{
	const AOdysseyCelestialBody* BA = GetBody(A);
	const AOdysseyCelestialBody* BB = GetBody(B);
	if (!BA || !BB || A == B)
	{
		return 0.0;
	}
	if (BA->RealDistanceFromEarthKm <= 0.0) return BB->RealDistanceFromEarthKm;
	if (BB->RealDistanceFromEarthKm <= 0.0) return BA->RealDistanceFromEarthKm;
	return FMath::Abs(BA->RealDistanceFromEarthKm - BB->RealDistanceFromEarthKm);
}

double AOdysseyTransitDirector::TransferHours(int32 A, int32 B) const
{
	if (A == B) return 0.0;
	return LegIsLong(A, B) ? 207.0 * 24.0 : 3.1 * 24.0;  // Hohmann-class Mars transfer, translunar coast
}

bool AOdysseyTransitDirector::BeginTravel(int32 TargetIndex)
{
	if (bTraveling || bAligning || !Vehicle || !GetBody(TargetIndex) || TargetIndex == Current)
	{
		return false;
	}
	PendingTarget = TargetIndex;
	bAligning = true;
	Telemetry.Phase = EOdysseyTransitPhase::Aligning;
	Telemetry.Origin = Current;
	Telemetry.Target = TargetIndex;
	Telemetry.Progress = 0.f;
	Telemetry.LegDistanceKm = RealDistanceKm(Current, TargetIndex);
	Telemetry.DistanceRemainingKm = Telemetry.LegDistanceKm;
	Telemetry.LegHours = TransferHours(Current, TargetIndex);
	Telemetry.MissionHours = 0.0;
	UE_LOG(LogOdysseySpace, Log, TEXT("transfer requested %d -> %d: aligning for the departure window"), Current, TargetIndex);
	return true;
}

void AOdysseyTransitDirector::StartTransfer()
{
	AOdysseyCelestialBody* O = GetBody(Current);
	AOdysseyCelestialBody* T = GetBody(PendingTarget);
	check(O && T && Vehicle);
	Target = PendingTarget;
	PendingTarget = INDEX_NONE;
	bAligning = false;

	const FVector DirOT = (T->GetActorLocation() - O->GetActorLocation()).GetSafeNormal();
	P0 = Vehicle->GetActorLocation();
	const FVector T0 = O->OrbitTangent(OrbitTheta);
	ArrivalTheta = T->OrbitAngleToward(-DirOT) + 0.55;
	P3 = T->OrbitPoint(ArrivalTheta);
	const FVector T3 = T->OrbitTangent(ArrivalTheta);
	const double L = FVector::Dist(P0, P3);
	const FVector Out0 = (P0 - O->GetActorLocation()).GetSafeNormal();
	const FVector Out3 = (P3 - T->GetActorLocation()).GetSafeNormal();
	P1 = P0 + T0 * L * 0.32 + Out0 * L * 0.06;
	P2 = P3 - T3 * L * 0.30 + Out3 * L * 0.05;

	// keep the path clear of every body: push the control points away from any intersected sphere
	for (int32 Iter = 0; Iter < 10 && !PathClear(P1, P2); ++Iter)
	{
		for (const AOdysseyCelestialBody* B : Bodies)
		{
			for (int32 i = 1; i < 64; ++i)
			{
				const FVector P = Bezier(i / 64.0);
				const FVector D = P - B->GetActorLocation();
				if (D.Size() < B->Radius * 1.04)
				{
					const FVector Push = D.GetSafeNormal() * B->Radius * 0.75;
					(i < 32 ? P1 : P2) += Push;
					break;
				}
			}
		}
	}

	ArcLength.SetNumUninitialized(ArcSamples + 1);
	ArcLength[0] = 0.0;
	FVector Prev = P0;
	for (int32 i = 1; i <= ArcSamples; ++i)
	{
		const FVector P = Bezier((double)i / ArcSamples);
		ArcLength[i] = ArcLength[i - 1] + FVector::Dist(P, Prev);
		Prev = P;
	}
	for (double& A : ArcLength)
	{
		A /= FMath::Max(1.0, ArcLength.Last());
	}

	LegUp = O->OrbitNormal();
	LegTime = 0.f;
	LegDuration = LegIsLong(Current, Target) ? LongLegSeconds : ShortLegSeconds;
	bTraveling = true;
	Telemetry.Phase = EOdysseyTransitPhase::DepartureBurn;
	SetView(EOdysseyDirectorView::Travel);
	ViewBlendDuration = 2.0f;
	OnDeparted.Broadcast(Current);
	UE_LOG(LogOdysseySpace, Log, TEXT("transfer %s -> %s started (%.0f s presentation, %.0f km)"),
		*O->DisplayName.ToString(), *T->DisplayName.ToString(), LegDuration, Telemetry.LegDistanceKm);
}

bool AOdysseyTransitDirector::PathClear(const FVector& InP1, const FVector& InP2) const
{
	for (int32 i = 1; i < 64; ++i)
	{
		const double S = i / 64.0;
		const double U = 1.0 - S;
		const FVector P = U * U * U * P0 + 3.0 * U * U * S * InP1 + 3.0 * U * S * S * InP2 + S * S * S * P3;
		for (const AOdysseyCelestialBody* B : Bodies)
		{
			if (FVector::Dist(P, B->GetActorLocation()) < B->Radius * 1.04)
			{
				return false;
			}
		}
	}
	return true;
}

FVector AOdysseyTransitDirector::Bezier(double S) const
{
	const double U = 1.0 - S;
	return U * U * U * P0 + 3.0 * U * U * S * P1 + 3.0 * U * S * S * P2 + S * S * S * P3;
}

FVector AOdysseyTransitDirector::BezierTangent(double S) const
{
	const double U = 1.0 - S;
	const FVector D = 3.0 * U * U * (P1 - P0) + 6.0 * U * S * (P2 - P1) + 3.0 * S * S * (P3 - P2);
	return D.GetSafeNormal();
}

double AOdysseyTransitDirector::ArcToBezierT(double S) const
{
	if (ArcLength.Num() < 2)
	{
		return S;
	}
	S = FMath::Clamp(S, 0.0, 1.0);
	int32 Lo = 0, Hi = ArcLength.Num() - 1;
	while (Hi - Lo > 1)
	{
		const int32 Mid = (Lo + Hi) / 2;
		(ArcLength[Mid] < S ? Lo : Hi) = Mid;
	}
	const double Span = FMath::Max(1e-9, ArcLength[Hi] - ArcLength[Lo]);
	return (Lo + (S - ArcLength[Lo]) / Span) / (ArcLength.Num() - 1);
}

void AOdysseyTransitDirector::Profile(float InU, double& S, double& Speed) const
{
	const double U = FMath::Clamp((double)InU, 0.0, 1.0);
	const double A = AccelFraction, D = DecelFraction, B = BaseSpeed;
	const double VMax = 1.0 / ((1.0 + B) * 0.5 * (A + D) + (1.0 - A - D));
	const double SA = VMax * A * (B + (1.0 - B) * 0.5);
	const double SC = SA + VMax * (1.0 - A - D);
	if (U < A)
	{
		const double X = U / A;
		S = VMax * A * (B * X + (1.0 - B) * RampArea(X));
		Speed = B + (1.0 - B) * Smooth(0.0, 1.0, X);
	}
	else if (U < 1.0 - D)
	{
		S = SA + VMax * (U - A);
		Speed = 1.0;
	}
	else
	{
		const double X = (U - (1.0 - D)) / D;
		S = SC + VMax * D * (X - (1.0 - B) * RampArea(X));
		Speed = 1.0 - (1.0 - B) * Smooth(0.0, 1.0, X);
	}
	S = FMath::Clamp(S, 0.0, 1.0);
}

void AOdysseyTransitDirector::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	SinceArrivalSeconds += DeltaSeconds;
	if (bTraveling)
	{
		TickTravel(DeltaSeconds);
	}
	else
	{
		TickParked(DeltaSeconds);
	}
	UpdateCamera(DeltaSeconds);
	KeepSkyOnCamera();
}

void AOdysseyTransitDirector::TickParked(float Dt)
{
	AOdysseyCelestialBody* B = GetBody(Current);
	if (!B || !Vehicle)
	{
		return;
	}
	double Speed = 1.0;
	if (bAligning)
	{
		const AOdysseyCelestialBody* T = GetBody(PendingTarget);
		const FVector DirOT = T ? (T->GetActorLocation() - B->GetActorLocation()).GetSafeNormal() : FVector::ForwardVector;
		const double Align = FVector::DotProduct(B->OrbitTangent(OrbitTheta), DirOT);
		Speed = Align > 0.62 ? 4.0 : 22.0;
		if (Align > 0.72)
		{
			StartTransfer();
			TickTravel(Dt);
			return;
		}
	}
	OrbitSpeedScale = FMath::FInterpTo(OrbitSpeedScale, Speed, Dt, bAligning ? 1.6 : 0.5);
	OrbitTheta += 2.0 * PI / FMath::Max(1.f, B->OrbitPeriodSeconds) * OrbitSpeedScale * Dt;
	const FVector P = B->OrbitPoint(OrbitTheta);
	const FVector Out = (P - B->GetActorLocation()).GetSafeNormal();
	Vehicle->SetActorLocation(P);
	const FQuat Want = FRotationMatrix::MakeFromXZ(B->OrbitTangent(OrbitTheta), Out).ToQuat();
	VehicleQuat = FMath::QInterpTo(VehicleQuat, Want, Dt, 0.6f);
	Vehicle->SetActorRotation(VehicleQuat);
	Vehicle->SetThrust(bAligning ? 0.0f : 0.f);
	Vehicle->SetRCS(bAligning ? 0.35f : 0.f);
}

void AOdysseyTransitDirector::TickTravel(float Dt)
{
	LegTime += Dt;
	const float U = FMath::Clamp(LegTime / LegDuration, 0.f, 1.f);
	double S = 0.0, Speed = 0.0;
	Profile(U, S, Speed);
	const double Bt = ArcToBezierT(S);
	const FVector P = Bezier(Bt);
	const FVector Fwd = BezierTangent(Bt);
	Vehicle->SetActorLocation(P);

	const double Flip = Smoother((U - FlipStart) / (FlipEnd - FlipStart));
	const FQuat Base = FRotationMatrix::MakeFromXZ(Fwd, LegUp).ToQuat();
	const FQuat Want = Base * FQuat(FVector::UpVector, PI * Flip);
	VehicleQuat = U < 0.02 ? FQuat::Slerp(VehicleQuat, Want, U / 0.02) : Want;
	Vehicle->SetActorRotation(VehicleQuat);

	EOdysseyTransitPhase Phase;
	if (U < AccelFraction) Phase = EOdysseyTransitPhase::DepartureBurn;
	else if (U < FlipStart) Phase = EOdysseyTransitPhase::Coast;
	else if (U < 1.0 - DecelFraction) Phase = EOdysseyTransitPhase::FlipManeuver;
	else Phase = EOdysseyTransitPhase::ArrivalBurn;
	const bool bBurn = Phase == EOdysseyTransitPhase::DepartureBurn || Phase == EOdysseyTransitPhase::ArrivalBurn;
	Vehicle->SetThrust(bBurn ? 1.f : 0.f);
	Vehicle->SetRCS(Phase == EOdysseyTransitPhase::FlipManeuver ? 1.f : 0.f);

	// presentation telemetry
	const bool bLong = LegIsLong(Telemetry.Origin, Target);
	const double OrbitalOrigin = GetBody(Telemetry.Origin) && GetBody(Telemetry.Origin)->BodyId == FName(TEXT("earth")) ? 7.67 :
		(GetBody(Telemetry.Origin) && GetBody(Telemetry.Origin)->BodyId == FName(TEXT("mars")) ? 3.36 : 1.63);
	const double OrbitalTarget = GetBody(Target) && GetBody(Target)->BodyId == FName(TEXT("earth")) ? 7.67 :
		(GetBody(Target) && GetBody(Target)->BodyId == FName(TEXT("mars")) ? 3.36 : 1.63);
	const double Peak = bLong ? 32.7 : 10.9;
	Telemetry.Phase = Phase;
	Telemetry.Target = Target;
	Telemetry.Progress = U;
	Telemetry.VelocityKms = FMath::Lerp(OrbitalOrigin, OrbitalTarget, (double)U) + (Peak - 0.5 * (OrbitalOrigin + OrbitalTarget)) * FMath::Clamp((Speed - BaseSpeed) / (1.0 - BaseSpeed), 0.0, 1.0);
	Telemetry.DistanceRemainingKm = Telemetry.LegDistanceKm * (1.0 - S);
	Telemetry.MissionHours = Telemetry.LegHours * S;

	if (LegTime >= LegDuration)
	{
		bTraveling = false;
		const int32 From = Current;
		Current = Target;
		OrbitTheta = ArrivalTheta;
		OrbitSpeedScale = 0.25;
		SinceArrivalSeconds = 0.f;
		Telemetry.Phase = EOdysseyTransitPhase::Parked;
		Telemetry.Origin = Current;
		Telemetry.Progress = 1.f;
		Telemetry.DistanceRemainingKm = 0.0;
		Vehicle->SetThrust(0.f);
		Vehicle->SetRCS(0.f);
		ViewBlendDuration = 3.0f;
		SetView(EOdysseyDirectorView::OrbitVista);
		OnArrived.Broadcast(Current);
		UE_LOG(LogOdysseySpace, Log, TEXT("arrived at %s from body %d (orbit radius %.0f)"),
			*GetBody(Current)->DisplayName.ToString(), From, GetBody(Current)->GetOrbitRadius());
	}
}

void AOdysseyTransitDirector::JumpToTravelProgress(float U)
{
	if (bTraveling)
	{
		LegTime = FMath::Clamp(U, 0.f, 0.999f) * LegDuration;
	}
}

void AOdysseyTransitDirector::SetView(EOdysseyDirectorView NewView)
{
	if (NewView == View)
	{
		return;
	}
	PreviousView = View;
	View = NewView;
	if (bHasCamera)
	{
		BlendFrom = LastCamera;
		ViewBlend = 0.f;
	}
	if (NewView != EOdysseyDirectorView::Travel)
	{
		ViewBlendDuration = FMath::Max(ViewBlendDuration, 2.5f);
	}
}

FTransform AOdysseyTransitDirector::MenuTransform(double T) const
{
	const AOdysseyCelestialBody* B = GetBody(Current);
	if (!B) return FTransform::Identity;
	const FVector C = B->GetActorLocation();
	const FVector Sun = SunDirection(GetWorld());
	const FVector Side = FVector::CrossProduct(Sun, FVector::UpVector).GetSafeNormal();
	FVector Dir = (Side + Sun * 0.42 + FVector::UpVector * 0.2).GetSafeNormal();
	Dir = FQuat(FVector::UpVector, 0.012 * T).RotateVector(Dir);
	const FVector Cam = C + Dir * B->Radius * 2.45;
	const FVector F = (C - Cam).GetSafeNormal();
	const FVector R = FVector::CrossProduct(FVector::UpVector, F).GetSafeNormal();
	const FVector Look = C - R * B->Radius * 0.62 + FVector::UpVector * B->Radius * 0.06;
	return FTransform(LookQuat(Cam, Look, FVector::UpVector), Cam);
}

FTransform AOdysseyTransitDirector::VistaTransform(double T) const
{
	const AOdysseyCelestialBody* B = GetBody(Current);
	if (!B || !Vehicle) return FTransform::Identity;
	const double L = Vehicle->Length;
	const FVector V = Vehicle->GetActorLocation();
	const FVector C = B->GetActorLocation();
	const FVector Out = (V - C).GetSafeNormal();
	const FVector Tan = B->OrbitTangent(OrbitTheta);
	const FVector N = B->OrbitNormal();
	const double A = 0.55 * FMath::Sin(T * 0.06);
	const FVector Cam = V + (-Tan * FMath::Cos(A) + N * FMath::Sin(A) * 0.7) * L * 2.9 + Out * L * 0.5;
	const FVector Look = V + (C - V).GetSafeNormal() * L * 0.35 + Tan * L * 0.25;
	return FTransform(LookQuat(Cam, Look, Out), Cam);
}

FTransform AOdysseyTransitDirector::PlanetTransform(double T) const
{
	const AOdysseyCelestialBody* B = GetBody(Current);
	if (!B) return FTransform::Identity;
	const FVector C = B->GetActorLocation();
	const FVector Sun = SunDirection(GetWorld());
	const FVector Side = FVector::CrossProduct(Sun, FVector::UpVector).GetSafeNormal();
	FVector Dir = (Sun * 0.75 + Side * 0.65 + FVector::UpVector * 0.22).GetSafeNormal();
	Dir = FQuat(FVector::UpVector, 0.02 * T).RotateVector(Dir);
	const FVector Cam = C + Dir * B->Radius * 3.1;
	return FTransform(LookQuat(Cam, C, FVector::UpVector), Cam);
}

FTransform AOdysseyTransitDirector::ShotTransform(int32 Shot, const FVector& V, const FVector& Fwd, const FVector& Up) const
{
	const double L = Vehicle ? Vehicle->Length : 6000.0;
	const FVector Right = FVector::CrossProduct(Up, Fwd).GetSafeNormal();
	const AOdysseyCelestialBody* T = GetBody(Target);
	const FVector TC = T ? T->GetActorLocation() : V + Fwd * 1e6;
	FVector Cam, Look;
	switch (Shot)
	{
	case 0:  // departure chase
		Cam = V - Fwd * L * 2.1 + Up * L * 0.55 + Right * L * 0.45;
		Look = V + Fwd * L * 1.3;
		break;
	case 1:  // over the shoulder toward the destination: vehicle in frame, target beyond it
	{
		const FVector D = (TC - V).GetSafeNormal();
		Cam = V - D * L * 2.4 + Up * L * 0.5 - Right * L * 0.85;
		Look = V + D * L * 3.0;
		break;
	}
	case 2:  // flip manoeuvre close-up
		Cam = V + Right * L * 1.35 + Up * L * 0.38 + Fwd * L * 0.2;
		Look = V;
		break;
	default:  // arrival reveal: vehicle against the destination
	{
		const FVector Out = (V - TC).GetSafeNormal();
		Cam = V + Out * L * 2.0 + Up * L * 0.55 - Right * L * 0.6;
		Look = V + (TC - V).GetSafeNormal() * L * 1.3;
		break;
	}
	}
	return FTransform(LookQuat(Cam, Look, Up), Cam);
}

void AOdysseyTransitDirector::UpdateCamera(float Dt)
{
	FTransform Want;
	float Fov = 55.f;
	switch (View)
	{
	case EOdysseyDirectorView::Menu:
		Want = MenuTransform(Clock);
		Fov = 42.f;
		break;
	case EOdysseyDirectorView::PlanetView:
		Want = PlanetTransform(Clock);
		Fov = 45.f;
		break;
	case EOdysseyDirectorView::Travel:
		if (bTraveling && Vehicle)
		{
			const float U = FMath::Clamp(LegTime / LegDuration, 0.f, 1.f);
			double S = 0.0, Speed = 0.0;
			Profile(U, S, Speed);
			const double Bt = ArcToBezierT(S);
			const FVector V = Vehicle->GetActorLocation();
			const FVector Fwd = BezierTangent(Bt);
			const double Edges[3] = {0.27, 0.62, 0.77};
			constexpr double F = 0.045;
			double W[4];
			for (int32 i = 0; i < 4; ++i)
			{
				const double In = i == 0 ? 1.0 : Smooth(Edges[i - 1] - F, Edges[i - 1] + F, U);
				const double Out = i == 3 ? 0.0 : Smooth(Edges[i] - F, Edges[i] + F, U);
				W[i] = In * (1.0 - Out);
			}
			FVector Loc = FVector::ZeroVector;
			FQuat Rot = ShotTransform(0, V, Fwd, LegUp).GetRotation();
			double Acc = 0.0;
			for (int32 i = 0; i < 4; ++i)
			{
				if (W[i] <= 1e-4) continue;
				const FTransform X = ShotTransform(i, V, Fwd, LegUp);
				Loc += X.GetLocation() * W[i];
				Acc += W[i];
				Rot = FQuat::Slerp(Rot, X.GetRotation(), W[i] / Acc);
			}
			Want = FTransform(Rot, Loc / FMath::Max(Acc, 1e-6));
			Fov = 58.f;
		}
		else
		{
			Want = VistaTransform(Clock);
		}
		break;
	default:
		Want = VistaTransform(Clock);
		break;
	}

	// never let the camera dip below a surface
	FVector Loc = Want.GetLocation();
	for (const AOdysseyCelestialBody* B : Bodies)
	{
		const FVector D = Loc - B->GetActorLocation();
		if (D.Size() < B->Radius * 1.01)
		{
			Loc = B->GetActorLocation() + D.GetSafeNormal() * B->Radius * 1.01;
		}
	}
	Want.SetLocation(Loc);

	FTransform Out = Want;
	if (ViewBlend < 1.f && bHasCamera)
	{
		ViewBlend = FMath::Min(1.f, ViewBlend + Dt / FMath::Max(0.1f, ViewBlendDuration));
		Out = Blend(BlendFrom, Want, Smoother(ViewBlend));
	}
	Camera->SetWorldLocationAndRotation(Out.GetLocation(), Out.GetRotation());
	Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, Fov, Dt, 1.5f));
	LastCamera = Out;
	bHasCamera = true;
}

void AOdysseyTransitDirector::KeepSkyOnCamera()
{
	const FVector C = Camera->GetComponentLocation();
	if (SkyActor)
	{
		SkyActor->SetActorLocation(C);
	}
	if (SunDiscActor)
	{
		SunDiscActor->SetActorLocation(C + SunDirection(GetWorld()) * SunDiscDistance);
	}
}
