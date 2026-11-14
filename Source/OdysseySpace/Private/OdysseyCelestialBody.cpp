#include "OdysseyCelestialBody.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	const FName SunParam(TEXT("SunDirection"));
}

AOdysseyCelestialBody::AOdysseyCelestialBody()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.f;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	Surface = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Surface"));
	Surface->SetupAttachment(Root);
	Surface->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Surface->SetCastShadow(false);
	Surface->bNeverDistanceCull = true;
	Surface->SetMobility(EComponentMobility::Movable);

	Atmosphere = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Atmosphere"));
	Atmosphere->SetupAttachment(Root);
	Atmosphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Atmosphere->SetCastShadow(false);
	Atmosphere->bNeverDistanceCull = true;
	Atmosphere->SetMobility(EComponentMobility::Movable);
}

void AOdysseyCelestialBody::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyScale();
}

void AOdysseyCelestialBody::ApplyScale()
{
	const double S = Radius / FMath::Max(1.0, (double)MeshRadius);
	Surface->SetRelativeScale3D(FVector(S));
	Atmosphere->SetRelativeScale3D(FVector(S * AtmosphereScale));
	Atmosphere->SetVisibility(Atmosphere->GetStaticMesh() != nullptr);
}

void AOdysseyCelestialBody::BeginPlay()
{
	Super::BeginPlay();
	ApplyScale();
	if (TActorIterator<ADirectionalLight> It(GetWorld()); It)
	{
		Sun = *It;
	}
	for (UStaticMeshComponent* C : {Surface.Get(), Atmosphere.Get()})
	{
		if (!C || !C->GetStaticMesh())
		{
			continue;
		}
		for (int32 i = 0; i < C->GetNumMaterials(); ++i)
		{
			if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(i))
			{
				Mids.Add(M);
			}
		}
	}
	PushSun();
}

void AOdysseyCelestialBody::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Surface->AddLocalRotation(FRotator(0.0, SpinDegreesPerSecond * DeltaSeconds, 0.0));
	PushSun();
}

FVector AOdysseyCelestialBody::GetSunDirection() const
{
	if (Sun)
	{
		return -Sun->GetActorForwardVector();
	}
	return FVector(-0.6, 0.7, 0.25).GetSafeNormal();
}

void AOdysseyCelestialBody::PushSun()
{
	const FVector S = GetSunDirection();
	const FLinearColor V(S.X, S.Y, S.Z, 0.f);
	for (UMaterialInstanceDynamic* M : Mids)
	{
		M->SetVectorParameterValue(SunParam, V);
	}
}

void AOdysseyCelestialBody::OrbitBasis(FVector& A, FVector& B) const
{
	const FQuat Tilt(FVector::ForwardVector, FMath::DegreesToRadians(OrbitInclination));
	A = FVector::ForwardVector;
	B = Tilt.RotateVector(FVector::RightVector);
}

FVector AOdysseyCelestialBody::OrbitNormal() const
{
	FVector A, B;
	OrbitBasis(A, B);
	return FVector::CrossProduct(A, B).GetSafeNormal();
}

FVector AOdysseyCelestialBody::OrbitPoint(double Theta) const
{
	FVector A, B;
	OrbitBasis(A, B);
	return GetActorLocation() + GetOrbitRadius() * (FMath::Cos(Theta) * A + FMath::Sin(Theta) * B);
}

FVector AOdysseyCelestialBody::OrbitTangent(double Theta) const
{
	FVector A, B;
	OrbitBasis(A, B);
	return (-FMath::Sin(Theta) * A + FMath::Cos(Theta) * B).GetSafeNormal();
}

double AOdysseyCelestialBody::OrbitAngleToward(const FVector& Dir) const
{
	FVector A, B;
	OrbitBasis(A, B);
	return FMath::Atan2(FVector::DotProduct(Dir, B), FVector::DotProduct(Dir, A));
}
