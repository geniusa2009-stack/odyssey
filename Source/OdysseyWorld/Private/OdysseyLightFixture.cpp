#include "OdysseyLightFixture.h"

#include "Components/RectLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"

AOdysseyLightFixture::AOdysseyLightFixture()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.05f;

	Fixture = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Fixture"));
	RootComponent = Fixture;
	Fixture->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Fixture->SetCanEverAffectNavigation(false);
	Fixture->CastShadow = false;

	Light = CreateDefaultSubobject<URectLightComponent>(TEXT("Light"));
	Light->SetupAttachment(Fixture);
	// Just below the diffuser, pointing down.
	Light->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -13.f), FRotator(-90.f, 0.f, 0.f));
	Light->SetMobility(EComponentMobility::Movable);
	Light->SourceWidth = 180.f;
	Light->SourceHeight = 40.f;
	Light->BarnDoorAngle = 60.f;
	Light->BarnDoorLength = 10.f;
}

void AOdysseyLightFixture::BeginPlay()
{
	Super::BeginPlay();
	BaseIntensity = Light->Intensity;
	EmissiveMaterials.Reset();
	for (int32 Slot = 0; Slot < Fixture->GetNumMaterials(); ++Slot)
	{
		const UMaterialInterface* M = Fixture->GetMaterial(Slot);
		float Unused = 0.f;
		if (M && M->GetScalarParameterValue(FHashedMaterialParameterInfo(EmissiveScaleParameter), Unused))
		{
			EmissiveMaterials.Add(Fixture->CreateDynamicMaterialInstance(Slot));
		}
	}
	LastFactor = -1.f;
	ApplyFactor(1.f);
}

void AOdysseyLightFixture::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Factor = BaseIntensity > KINDA_SMALL_NUMBER ? Light->Intensity / BaseIntensity : 0.f;
	ApplyFactor(Factor);
}

void AOdysseyLightFixture::ApplyFactor(float Factor)
{
	if (FMath::IsNearlyEqual(Factor, LastFactor, 0.002f))
	{
		return;
	}
	LastFactor = Factor;
	for (UMaterialInstanceDynamic* MID : EmissiveMaterials)
	{
		if (MID)
		{
			MID->SetScalarParameterValue(EmissiveScaleParameter, Factor);
		}
	}
}
