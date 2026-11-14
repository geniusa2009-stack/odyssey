#include "OdysseyTransitVehicle.h"

#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const FName ThrustParam(TEXT("Thrust"));
	const FName NavParam(TEXT("NavBlink"));
}

AOdysseyTransitVehicle::AOdysseyTransitVehicle()
{
	PrimaryActorTick.bCanEverTick = true;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	Hull = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Hull"));
	Hull->SetupAttachment(Root);
	Hull->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Hull->SetMobility(EComponentMobility::Movable);
	Hull->bNeverDistanceCull = true;

	Plume = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Plume"));
	Plume->SetupAttachment(Hull);
	Plume->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Plume->SetCastShadow(false);
	Plume->SetMobility(EComponentMobility::Movable);

	RCS = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RCS"));
	RCS->SetupAttachment(Hull);
	RCS->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RCS->SetCastShadow(false);
	RCS->SetMobility(EComponentMobility::Movable);

	EngineLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("EngineLight"));
	EngineLight->SetupAttachment(Hull);
	EngineLight->SetRelativeLocation(FVector(-4200.0, 0.0, 0.0));
	EngineLight->SetMobility(EComponentMobility::Movable);
	EngineLight->SetLightColor(FLinearColor(0.55f, 0.82f, 1.0f));
	EngineLight->SetAttenuationRadius(9000.f);
	EngineLight->SetIntensity(0.f);
	EngineLight->SetCastShadows(false);
}

void AOdysseyTransitVehicle::BeginPlay()
{
	Super::BeginPlay();
	if (Plume->GetStaticMesh())
	{
		PlumeMid = Plume->CreateDynamicMaterialInstance(0);
	}
	if (RCS->GetStaticMesh())
	{
		RcsMid = RCS->CreateDynamicMaterialInstance(0);
	}
	for (int32 i = 0; i < Hull->GetNumMaterials(); ++i)
	{
		UMaterialInterface* M = Hull->GetMaterial(i);
		FMaterialParameterInfo Info(NavParam);
		float Unused = 0.f;
		if (M && M->GetScalarParameterValue(Info, Unused))
		{
			if (UMaterialInstanceDynamic* D = Hull->CreateDynamicMaterialInstance(i))
			{
				HullMids.Add(D);
			}
		}
	}
}

void AOdysseyTransitVehicle::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Clock += DeltaSeconds;
	Thrust = FMath::FInterpTo(Thrust, TargetThrust, DeltaSeconds, 2.6f);
	RcsLevel = FMath::FInterpTo(RcsLevel, TargetRCS, DeltaSeconds, 10.f);

	// subtle combustion flicker
	const float Flicker = 1.f + 0.035f * FMath::Sin(Clock * 47.f) + 0.02f * FMath::Sin(Clock * 83.f + 1.3f);
	const float T = Thrust * Flicker;
	Plume->SetVisibility(Thrust > 0.01f);
	Plume->SetRelativeScale3D(FVector(0.25 + 0.75 * T, 0.85 + 0.15 * T, 0.85 + 0.15 * T));
	if (PlumeMid)
	{
		PlumeMid->SetScalarParameterValue(ThrustParam, T);
	}
	EngineLight->SetIntensity(EngineLightIntensity * T);

	// RCS: short pulses while a manoeuvre is commanded
	const float Pulse = RcsLevel * (FMath::Sin(Clock * 21.f) > 0.2f ? 1.f : 0.15f);
	RCS->SetVisibility(Pulse > 0.02f);
	if (RcsMid)
	{
		RcsMid->SetScalarParameterValue(ThrustParam, Pulse);
	}

	// navigation strobes: short double flash
	const float Phase = FMath::Fmod(Clock, NavBlinkPeriod) / NavBlinkPeriod;
	const float Nav = (Phase < 0.05f || (Phase > 0.12f && Phase < 0.17f)) ? 1.f : 0.f;
	for (UMaterialInstanceDynamic* M : HullMids)
	{
		M->SetScalarParameterValue(NavParam, Nav);
	}
}
