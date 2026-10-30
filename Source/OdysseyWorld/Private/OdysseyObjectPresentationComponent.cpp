// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyObjectPresentationComponent.h"

#include "Components/LightComponent.h"
#include "GameFramework/Actor.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseySemanticBindingComponent.h"

UOdysseyObjectPresentationComponent::UOdysseyObjectPresentationComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
	PowerIntensityScale.Add(TEXT("off"), 0.f);
	PowerIntensityScale.Add(TEXT("shed"), 0.f);
	PowerIntensityScale.Add(TEXT("degraded"), 0.35f);
	StatusIntensityScale.Add(TEXT("damaged"), 0.5f);
	StatusIntensityScale.Add(TEXT("offline"), 0.f);
}

FName UOdysseyObjectPresentationComponent::GetObjectId() const
{
	const UOdysseySemanticBindingComponent* B = GetOwner()->FindComponentByClass<UOdysseySemanticBindingComponent>();
	return B ? B->SemanticId : NAME_None;
}

void UOdysseyObjectPresentationComponent::BeginPlay()
{
	Super::BeginPlay();
	TArray<ULightComponent*> Found;
	GetOwner()->GetComponents<ULightComponent>(Found);
	for (AActor* Extra : ExtraLightActors)
	{
		if (Extra)
		{
			TArray<ULightComponent*> More;
			Extra->GetComponents<ULightComponent>(More);
			Found.Append(More);
		}
	}
	for (ULightComponent* L : Found)
	{
		FLightState S;
		S.Light = L;
		S.BaseIntensity = L->Intensity;
		S.bWarning = L->ComponentHasTag(WarningLightTag);
		Lights.Add(S);
	}
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		if (UOdysseyEventRouter* R = B->GetEventRouter())
		{
			R->OnSystemStateChanged.AddDynamic(this, &UOdysseyObjectPresentationComponent::HandleSystem);
			R->OnIncident.AddDynamic(this, &UOdysseyObjectPresentationComponent::HandleIncident);
			R->OnInteractionsRefreshed.AddDynamic(this, &UOdysseyObjectPresentationComponent::HandleRefreshed);
			R->OnSnapshotApplied.AddDynamic(this, &UOdysseyObjectPresentationComponent::HandleSnapshot);
		}
	}
	Refresh();
}

void UOdysseyObjectPresentationComponent::HandleSystem(const FOdysseySystemStateEvent& E)
{
	if (E.ObjectId == GetObjectId()) Refresh();
}

void UOdysseyObjectPresentationComponent::HandleIncident(const FOdysseyIncidentEvent& E)
{
	if (E.InvolvedObjects.Contains(GetObjectId())) Refresh();
}

void UOdysseyObjectPresentationComponent::HandleRefreshed(FName ObjectId)
{
	if (ObjectId == GetObjectId()) Refresh();
}

void UOdysseyObjectPresentationComponent::HandleSnapshot(FName)
{
	Refresh();
}

void UOdysseyObjectPresentationComponent::Refresh()
{
	const UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this);
	if (!B)
	{
		return;
	}
	const FOdysseyObjectView View = B->GetObjectView(GetObjectId());
	if (!View.bFound)
	{
		return;  // not (yet) revealed by the backend: keep the authored look
	}
	const float* P = PowerIntensityScale.Find(View.Power);
	const float* S = StatusIntensityScale.Find(View.Status);
	const float Scale = (P ? *P : 1.f) * (S ? *S : 1.f);
	const bool bIncident = View.ActiveIncidents.Num() > 0;
	for (FLightState& L : Lights)
	{
		if (!L.Light.IsValid()) continue;
		L.From = L.Light->Intensity / FMath::Max(L.BaseIntensity, KINDA_SMALL_NUMBER);
		L.To = L.bWarning ? (bIncident ? 1.f : 0.f) : Scale;
	}
	BlendAlpha = 0.f;
	SetComponentTickEnabled(true);
	Current = View;
	OnObjectStateChanged(View, bIncident);
}

void UOdysseyObjectPresentationComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	BlendAlpha = BlendSeconds <= 0.f ? 1.f : FMath::Min(1.f, BlendAlpha + DeltaTime / BlendSeconds);
	for (FLightState& L : Lights)
	{
		if (L.Light.IsValid())
		{
			L.Light->SetIntensity(L.BaseIntensity * FMath::InterpEaseInOut(L.From, L.To, BlendAlpha, 2.f));
		}
	}
	if (BlendAlpha >= 1.f)
	{
		SetComponentTickEnabled(false);
	}
}
