#include "OdysseyHoloTable.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "OdysseyBackendSubsystem.h"

namespace
{
	const FName PColor(TEXT("Color"));
	const FName PIntensity(TEXT("Intensity"));
	const FName PSource(TEXT("Source"));
	const FName PUseTexture(TEXT("UseTexture"));
	constexpr int32 NumBeads = 36;

	const FLinearColor IonColor(0.10f, 0.52f, 0.66f);
	const FLinearColor AlertColor(0.78f, 0.13f, 0.08f);
	const FLinearColor AmberColor(0.70f, 0.36f, 0.05f);

	UStaticMeshComponent* Part(AActor* Owner, USceneComponent* Parent, const TCHAR* Name)
	{
		UStaticMeshComponent* C = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		C->SetupAttachment(Parent);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCastShadow(false);
		C->SetMobility(EComponentMobility::Movable);
		return C;
	}

	float Ramp(float T, float A, float B)
	{
		const float X = FMath::Clamp((T - A) / (B - A), 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}
}

AOdysseyHoloTable::AOdysseyHoloTable()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;
	Beam = Part(this, Root, TEXT("Beam"));
	ScanDisc = Part(this, Root, TEXT("ScanDisc"));
	Bodies0 = Part(this, Root, TEXT("Earth"));
	Bodies1 = Part(this, Root, TEXT("Moon"));
	Bodies2 = Part(this, Root, TEXT("Mars"));
	MoonOrbit = Part(this, Root, TEXT("MoonOrbit"));
	StationRing = Part(this, Root, TEXT("StationRing"));
	SelectRing = Part(this, Root, TEXT("SelectRing"));
	Craft = Part(this, Root, TEXT("Craft"));
	StationMarker = Part(this, Root, TEXT("StationMarker"));
	Beads = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Trajectory"));
	Beads->SetupAttachment(Root);
	Beads->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Beads->SetCastShadow(false);
	Beads->SetMobility(EComponentMobility::Movable);

	Title = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Title"));
	Title->SetupAttachment(Root);
	Title->SetHorizontalAlignment(EHTA_Center);
	Title->SetWorldSize(9.f);
	Title->SetRelativeRotation(FRotator(0.0, -90.0, 0.0));
	Detail = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Detail"));
	Detail->SetupAttachment(Root);
	Detail->SetHorizontalAlignment(EHTA_Center);
	Detail->SetWorldSize(5.f);
	Detail->SetRelativeRotation(FRotator(0.0, -90.0, 0.0));
}

UMaterialInstanceDynamic* AOdysseyHoloTable::Mid(UStaticMeshComponent* C)
{
	if (!C || !C->GetStaticMesh() || !HoloMaterial)
	{
		return nullptr;
	}
	C->SetMaterial(0, HoloMaterial);
	return C->CreateDynamicMaterialInstance(0);
}

void AOdysseyHoloTable::BeginPlay()
{
	Super::BeginPlay();
	const auto Assign = [](UStaticMeshComponent* C, UStaticMesh* M) { if (M) C->SetStaticMesh(M); };
	Assign(Beam, BeamMesh);
	Assign(ScanDisc, DiscMesh);
	Assign(Bodies0, SphereMesh);
	Assign(Bodies1, SphereMesh);
	Assign(Bodies2, SphereMesh);
	Assign(MoonOrbit, RingMesh);
	Assign(StationRing, RingMesh);
	Assign(SelectRing, RingMesh);
	Assign(Craft, MarkerMesh);
	Assign(StationMarker, MarkerMesh);
	if (BeadMesh)
	{
		Beads->SetStaticMesh(BeadMesh);
		if (HoloMaterial) Beads->SetMaterial(0, HoloMaterial);
		BeadMid = Beads->CreateDynamicMaterialInstance(0);
		for (int32 i = 0; i < NumBeads; ++i)
		{
			Beads->AddInstance(FTransform::Identity);
		}
	}
	UTexture* Tex[3] = {EarthTexture, MoonTexture, MarsTexture};
	UStaticMeshComponent* B[3] = {Bodies0, Bodies1, Bodies2};
	for (int32 i = 0; i < 3; ++i)
	{
		UMaterialInstanceDynamic* M = Mid(B[i]);
		if (M && Tex[i])
		{
			M->SetTextureParameterValue(PSource, Tex[i]);
			M->SetScalarParameterValue(PUseTexture, 1.f);
		}
		BodyMids.Add(M);
	}
	BeamMid = Mid(Beam);
	DiscMid = Mid(ScanDisc);
	OrbitMid = Mid(MoonOrbit);
	StationRingMid = Mid(StationRing);
	SelectMid = Mid(SelectRing);
	CraftMid = Mid(Craft);
	MarkerMid = Mid(StationMarker);
	SetState(bAutoProgram ? EOdysseyHoloState::Boot : EOdysseyHoloState::Off);
}

void AOdysseyHoloTable::SetState(EOdysseyHoloState NewState)
{
	if (NewState != State)
	{
		State = NewState;
		StateTime = 0.f;
	}
}

void AOdysseyHoloTable::SelectDestination(int32 Index)
{
	Destination = FMath::Clamp(Index, 1, 2);
}

void AOdysseyHoloTable::PollBackend(float Dt)
{
	PollClock += Dt;
	if (!bFollowBackendIncidents || PollClock < 0.5f)
	{
		return;
	}
	PollClock = 0.f;
	const UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this);
	if (!B || !B->IsSessionReady())
	{
		return;
	}
	const TArray<FOdysseyIncidentView> Incidents = B->GetIncidents(true);
	const bool bNow = Incidents.Num() > 0;
	if (bNow)
	{
		const FOdysseyIncidentView& I = Incidents[0];
		IncidentText = I.InvolvedObjects.Num() > 0 ? I.InvolvedObjects[0].ToString() : I.Id.ToString();
		IncidentText = IncidentText.Replace(TEXT("earth.command."), TEXT("")).Replace(TEXT("."), TEXT(" / ")).Replace(TEXT("_"), TEXT(" ")).ToUpper();
	}
	if (bNow && !bIncidentActive)
	{
		SetState(EOdysseyHoloState::Incident);
	}
	else if (!bNow && bIncidentActive)
	{
		SetState(EOdysseyHoloState::Resolved);
	}
	bIncidentActive = bNow;
}

void AOdysseyHoloTable::Advance(float Dt)
{
	StateTime += Dt;
	if (!bAutoProgram || bIncidentActive)
	{
		return;
	}
	switch (State)
	{
	case EOdysseyHoloState::Boot:            if (StateTime > 3.2f) SetState(EOdysseyHoloState::EarthOverview); break;
	case EOdysseyHoloState::EarthOverview:   if (StateTime > 12.f) SetState(EOdysseyHoloState::MissionPlanning); break;
	case EOdysseyHoloState::MissionPlanning:
		if (StateTime > 10.f) SetState(EOdysseyHoloState::Trajectory);
		Destination = StateTime < 5.f ? 1 : 2;
		break;
	case EOdysseyHoloState::Trajectory:      if (StateTime > 9.f) SetState(EOdysseyHoloState::Simulation); break;
	case EOdysseyHoloState::Simulation:
		if (StateTime > 14.f)
		{
			Destination = Destination == 1 ? 2 : 1;
			SetState(EOdysseyHoloState::EarthOverview);
		}
		break;
	case EOdysseyHoloState::Resolved:        if (StateTime > 5.f) SetState(EOdysseyHoloState::EarthOverview); break;
	default: break;
	}
}

AOdysseyHoloTable::FLayout AOdysseyHoloTable::TargetLayout() const
{
	FLayout L;
	const float R = VolumeRadius;
	const bool bSystem = State == EOdysseyHoloState::MissionPlanning || State == EOdysseyHoloState::Trajectory || State == EOdysseyHoloState::Simulation;
	if (bSystem)
	{
		L.Pos[0] = FVector(-0.52f * R, -0.1f * R, -0.08f * R);
		L.Pos[1] = FVector(0.0f, 0.42f * R, 0.12f * R);
		L.Pos[2] = FVector(0.6f * R, -0.28f * R, 0.0f);
		L.Radius[0] = 0.2f * R; L.Radius[1] = 0.07f * R; L.Radius[2] = 0.12f * R;
		L.BodyAlpha[0] = L.BodyAlpha[1] = L.BodyAlpha[2] = 1.f;
		L.OrbitAlpha = 1.f;
		L.TrajectoryAlpha = State == EOdysseyHoloState::MissionPlanning ? 0.f : 1.f;
		L.CraftAlpha = 1.f;
	}
	else
	{
		L.Pos[0] = FVector::ZeroVector;
		L.Pos[1] = FVector(0.75f * R, 0.35f * R, 0.15f * R);
		L.Pos[2] = FVector(0.9f * R, -0.4f * R, 0.f);
		L.Radius[0] = 0.4f * R; L.Radius[1] = 0.02f * R; L.Radius[2] = 0.02f * R;
		L.BodyAlpha[0] = State == EOdysseyHoloState::Off ? 0.f : 1.f;
		L.BodyAlpha[1] = L.BodyAlpha[2] = 0.f;
		L.StationAlpha = State == EOdysseyHoloState::Off || State == EOdysseyHoloState::Boot ? 0.f : 1.f;
		L.CraftAlpha = L.StationAlpha;
	}
	return L;
}

FVector AOdysseyHoloTable::Arc(float T) const
{
	const FVector A = Current.Pos[0];
	const FVector B = Current.Pos[Destination];
	const FVector M = (A + B) * 0.5f + FVector(0.0, 0.0, VolumeRadius * 0.38f);
	const float U = 1.f - T;
	return U * U * A + 2.f * U * T * M + T * T * B;
}

void AOdysseyHoloTable::Param(UMaterialInstanceDynamic* M, float Intensity, const FLinearColor& Color) const
{
	if (M)
	{
		M->SetScalarParameterValue(PIntensity, Intensity);
		M->SetVectorParameterValue(PColor, Color);
	}
}

void AOdysseyHoloTable::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	PollBackend(DeltaSeconds);
	Advance(DeltaSeconds);
	Apply(DeltaSeconds);
}

void AOdysseyHoloTable::Apply(float Dt)
{
	// presence, alert colouring, layout blending
	const float WantPower = State == EOdysseyHoloState::Off ? 0.f : (State == EOdysseyHoloState::Boot ? Ramp(StateTime, 0.4f, 2.6f) : 1.f);
	Power = FMath::FInterpTo(Power, WantPower, Dt, 3.f);
	Alert = FMath::FInterpTo(Alert, State == EOdysseyHoloState::Incident ? 1.f : 0.f, Dt, 2.f);
	const FLayout T = TargetLayout();
	if (!bLayoutInit)
	{
		Current = T;
		bLayoutInit = true;
	}
	const float K = FMath::Clamp(Dt * 2.4f, 0.f, 1.f);
	for (int32 i = 0; i < 3; ++i)
	{
		Current.Pos[i] = FMath::Lerp(Current.Pos[i], T.Pos[i], K);
		Current.Radius[i] = FMath::Lerp(Current.Radius[i], T.Radius[i], K);
		Current.BodyAlpha[i] = FMath::Lerp(Current.BodyAlpha[i], T.BodyAlpha[i], K);
	}
	Current.OrbitAlpha = FMath::Lerp(Current.OrbitAlpha, T.OrbitAlpha, K);
	Current.TrajectoryAlpha = FMath::Lerp(Current.TrajectoryAlpha, T.TrajectoryAlpha, K);
	Current.StationAlpha = FMath::Lerp(Current.StationAlpha, T.StationAlpha, K);
	Current.CraftAlpha = FMath::Lerp(Current.CraftAlpha, T.CraftAlpha, K);

	const FLinearColor Base = FMath::Lerp(IonColor, AlertColor, Alert);
	const float Flicker = 0.94f + 0.06f * FMath::Sin(Clock * 31.f) * FMath::Sin(Clock * 7.3f);
	const float P = Power * Flicker;
	const FVector C(0.0, 0.0, VolumeHeight);

	// projection beam and scan disc (the disc sweeps up through the volume while booting)
	Beam->SetRelativeLocation(FVector(0.0, 0.0, 2.0));
	Beam->SetRelativeScale3D(FVector(VolumeRadius / 100.f * 0.95f, VolumeRadius / 100.f * 0.95f, (VolumeHeight + VolumeRadius * 0.6f) / 100.f));
	Param(BeamMid, 0.6f * P, Base);
	const float Sweep = State == EOdysseyHoloState::Boot ? Ramp(StateTime, 0.2f, 2.8f) : 0.5f + 0.5f * FMath::Sin(Clock * 0.6f);
	ScanDisc->SetRelativeLocation(C + FVector(0.0, 0.0, (Sweep - 0.5f) * VolumeRadius * 1.2f));
	ScanDisc->SetRelativeScale3D(FVector(VolumeRadius / 100.f * 1.05f, VolumeRadius / 100.f * 1.05f, 1.f));
	Param(DiscMid, (State == EOdysseyHoloState::Boot ? 2.2f : 0.7f) * P, Base);

	// bodies
	UStaticMeshComponent* B[3] = {Bodies0, Bodies1, Bodies2};
	const float Spin[3] = {14.f, 6.f, 9.f};
	for (int32 i = 0; i < 3; ++i)
	{
		const float A = Current.BodyAlpha[i] * P;
		B[i]->SetVisibility(A > 0.01f && Current.Radius[i] > 0.5f);
		B[i]->SetRelativeLocation(C + Current.Pos[i]);
		B[i]->SetRelativeScale3D(FVector(Current.Radius[i] / 100.f));
		B[i]->SetRelativeRotation(FRotator(0.0, Clock * Spin[i], 0.0));
		FLinearColor Tint = i == 0 ? FMath::Lerp(FLinearColor(0.35f, 0.75f, 0.95f), AlertColor, Alert) : (i == 1 ? FLinearColor(0.6f, 0.75f, 0.85f) : FLinearColor(0.85f, 0.45f, 0.25f));
		const bool bSelected = (State == EOdysseyHoloState::MissionPlanning || State == EOdysseyHoloState::Trajectory || State == EOdysseyHoloState::Simulation) && i == Destination;
		Param(BodyMids.IsValidIndex(i) ? BodyMids[i].Get() : nullptr, A * (bSelected ? 1.5f : 1.f) * 4.2f, Tint);
	}

	// Moon orbit around Earth (system view)
	const float OrbitR = FVector::Dist(Current.Pos[0], Current.Pos[1]);
	MoonOrbit->SetRelativeLocation(C + Current.Pos[0]);
	MoonOrbit->SetRelativeScale3D(FVector(OrbitR / 100.f, OrbitR / 100.f, 1.f));
	MoonOrbit->SetVisibility(Current.OrbitAlpha * P > 0.01f);
	Param(OrbitMid, 2.6f * Current.OrbitAlpha * P, Base);

	// destination selection ring pulses around the chosen body
	const float Pulse = 0.5f + 0.5f * FMath::Sin(Clock * 4.f);
	const float SelR = Current.Radius[Destination] * (1.6f + 0.15f * Pulse);
	SelectRing->SetRelativeLocation(C + Current.Pos[Destination]);
	SelectRing->SetRelativeScale3D(FVector(SelR / 100.f, SelR / 100.f, 1.f));
	SelectRing->SetRelativeRotation(FRotator(0.0, Clock * 40.f, 0.0));
	SelectRing->SetVisibility(Current.OrbitAlpha * P > 0.01f);
	Param(SelectMid, (1.8f + 1.8f * Pulse) * Current.OrbitAlpha * P, FMath::Lerp(Base, AmberColor, 0.35f));

	// station ring + marker around Earth (overview / incident)
	const float StationR = Current.Radius[0] * 1.18f;
	StationRing->SetRelativeLocation(C + Current.Pos[0]);
	StationRing->SetRelativeScale3D(FVector(StationR / 100.f, StationR / 100.f, 1.f));
	StationRing->SetRelativeRotation(FRotator(18.0, Clock * 10.f, 0.0));
	StationRing->SetVisibility(Current.StationAlpha * P > 0.01f);
	Param(StationRingMid, 2.4f * Current.StationAlpha * P, Base);
	const float MarkerA = Current.StationAlpha * P * (Alert > 0.5f ? (0.4f + 0.6f * Pulse) : 1.f);
	StationMarker->SetRelativeLocation(C + Current.Pos[0] + FVector(Current.Radius[0] * 0.55f, -Current.Radius[0] * 0.62f, Current.Radius[0] * 0.55f));
	StationMarker->SetRelativeScale3D(FVector(0.05f + 0.04f * Alert * Pulse));
	StationMarker->SetVisibility(MarkerA > 0.01f);
	Param(MarkerMid, 7.f * MarkerA, FMath::Lerp(FLinearColor(0.9f, 0.9f, 0.85f), AlertColor, Alert));

	// transit vehicle marker: parking orbit in overview, flying the arc in simulation
	FVector CraftPos;
	if (State == EOdysseyHoloState::Simulation)
	{
		const float S = FMath::Fmod(StateTime / 6.f, 1.f);
		CraftPos = Arc(S);
	}
	else if (State == EOdysseyHoloState::Trajectory)
	{
		CraftPos = Arc(0.f) + FVector(0.0, 0.0, Current.Radius[0] * 0.25f * (1.f + Pulse));
	}
	else
	{
		const float A = Clock * 0.7f;
		const float Rr = Current.Radius[0] * 1.3f;
		CraftPos = Current.Pos[0] + FVector(FMath::Cos(A) * Rr, FMath::Sin(A) * Rr, FMath::Sin(A) * Rr * 0.3f);
	}
	Craft->SetRelativeLocation(C + CraftPos);
	Craft->SetRelativeScale3D(FVector(0.035f));
	Craft->SetRelativeRotation(FRotator(0.0, Clock * 90.f, 45.0));
	Craft->SetVisibility(Current.CraftAlpha * P > 0.01f);
	Param(CraftMid, 6.f * Current.CraftAlpha * P, FLinearColor(0.95f, 0.95f, 0.9f));

	// trajectory beads flowing toward the destination
	if (Beads->GetInstanceCount() == NumBeads)
	{
		const float Flow = State == EOdysseyHoloState::Simulation ? 0.22f : 0.08f;
		for (int32 i = 0; i < NumBeads; ++i)
		{
			const float S = FMath::Fmod((float)i / NumBeads + Clock * Flow, 1.f);
			const float Size = 0.012f * (0.6f + 0.4f * FMath::Sin(S * PI)) * FMath::Max(Current.TrajectoryAlpha, 0.001f);
			Beads->UpdateInstanceTransform(i, FTransform(FQuat::Identity, C + Arc(S), FVector(Size)), false, i == NumBeads - 1, true);
		}
		Beads->SetVisibility(Current.TrajectoryAlpha * P > 0.01f);
		Param(BeadMid, 6.f * Current.TrajectoryAlpha * P, FMath::Lerp(Base, FLinearColor(0.9f, 0.95f, 1.f), 0.3f));
	}

	// labels
	FString Head, Sub;
	switch (State)
	{
	case EOdysseyHoloState::Off: break;
	case EOdysseyHoloState::Boot: Head = TEXT("ODYSSEY MISSION TABLE"); Sub = TEXT("INITIALISING PROJECTION"); break;
	case EOdysseyHoloState::EarthOverview: Head = TEXT("EARTH / SOL III"); Sub = TEXT("EARTH COMMAND  -  STATION NOMINAL"); break;
	case EOdysseyHoloState::MissionPlanning: Head = TEXT("MISSION PLANNING"); Sub = Destination == 1 ? TEXT("DESTINATION  LUNA  /  3.1 D TRANSFER") : TEXT("DESTINATION  MARS  /  207 D TRANSFER"); break;
	case EOdysseyHoloState::Trajectory: Head = TEXT("TRANSFER TRAJECTORY"); Sub = Destination == 1 ? TEXT("EARTH  >  LUNA") : TEXT("EARTH  >  MARS"); break;
	case EOdysseyHoloState::Simulation: Head = TEXT("SIMULATION"); Sub = TEXT("OTV-1 MERIDIAN  -  DEPARTURE / COAST / FLIP / INSERTION"); break;
	case EOdysseyHoloState::Incident: Head = TEXT("INCIDENT"); Sub = IncidentText.IsEmpty() ? FString(TEXT("STATION SYSTEMS")) : IncidentText; break;
	case EOdysseyHoloState::Resolved: Head = TEXT("RESOLVED"); Sub = TEXT("STATION SYSTEMS NOMINAL"); break;
	}
	const FColor TextColor = (FMath::Lerp(FLinearColor(0.55f, 0.85f, 0.95f), FLinearColor(1.f, 0.35f, 0.25f), Alert) * FMath::Max(0.f, P)).ToFColor(true);
	Title->SetText(FText::FromString(Head));
	Title->SetTextRenderColor(TextColor);
	Title->SetRelativeLocation(C + FVector(0.0, -VolumeRadius * 0.15f, VolumeRadius * 0.82f));
	Detail->SetText(FText::FromString(Sub));
	Detail->SetTextRenderColor(TextColor);
	Detail->SetRelativeLocation(C + FVector(0.0, -VolumeRadius * 0.15f, VolumeRadius * 0.7f));
}
