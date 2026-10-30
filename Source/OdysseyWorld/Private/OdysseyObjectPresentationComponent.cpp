// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyObjectPresentationComponent.h"

#include "Components/LightComponent.h"
#include "GameFramework/Actor.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseySemanticBindingComponent.h"
#include "OdysseyStringConv.h"

#include "OdysseyProtocol/PresentationRules.h"

namespace
{
odyssey::presentation::LightRule ToNative(const FOdysseyLightRule& R)
{
	odyssey::presentation::LightRule N;
	for (const TPair<FName, float>& P : R.PowerScale) N.power[OdysseyConv::ToStd(P.Key)] = P.Value;
	for (const TPair<FName, float>& P : R.ModeScale) N.mode[OdysseyConv::ToStd(P.Key)] = P.Value;
	for (const TPair<FName, float>& P : R.StatusScale) N.status[OdysseyConv::ToStd(P.Key)] = P.Value;
	N.warning = R.bWarning;
	return N;
}
}  // namespace

UOdysseyObjectPresentationComponent::UOdysseyObjectPresentationComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;
	// Default for the owner's own lights: an equipment indicator (map definition rule "equipment").
	OwnLightRule.PowerScale.Add(TEXT("off"), 0.f);
	OwnLightRule.ModeScale.Add(TEXT("eco"), 0.5f);
	OwnLightRule.StatusScale.Add(TEXT("offline"), 0.f);
	OwnLightRule.StatusScale.Add(TEXT("damaged"), 0.4f);
}

FName UOdysseyObjectPresentationComponent::GetObjectId() const
{
	const UOdysseySemanticBindingComponent* B = GetOwner()->FindComponentByClass<UOdysseySemanticBindingComponent>();
	return B ? B->SemanticId : NAME_None;
}

float UOdysseyObjectPresentationComponent::GetGroupScale(FName GroupName) const
{
	const float* S = GroupScale.Find(GroupName);
	return S ? *S : 1.f;
}

void UOdysseyObjectPresentationComponent::BeginPlay()
{
	Super::BeginPlay();
	auto Collect = [this](AActor* From, int32 Group) {
		TArray<ULightComponent*> Found;
		From->GetComponents<ULightComponent>(Found);
		for (ULightComponent* L : Found)
		{
			FLightState S;
			S.Light = L;
			S.Group = Group;
			S.bOwnWarning = Group == INDEX_NONE && L->ComponentHasTag(WarningLightTag);
			S.BaseIntensity = L->Intensity;
			Lights.Add(S);
		}
	};
	Collect(GetOwner(), INDEX_NONE);
	for (int32 G = 0; G < LightGroups.Num(); ++G)
	{
		for (AActor* A : LightGroups[G].LightActors)
		{
			if (A) Collect(A, G);
		}
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
	// started/updated/resolved: warning lights depend on it even after the object leaves the list
	if (E.InvolvedObjects.Contains(GetObjectId()) || E.bResolved) Refresh();
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
	const odyssey::MirrorModel* M = B ? B->GetMirrorModel() : nullptr;
	if (!M)
	{
		return;
	}
	const std::string Id = OdysseyConv::ToStd(GetObjectId());
	if (!M->object(Id))
	{
		return;  // not (yet) revealed by the backend: keep the authored look
	}
	// The same pure function the native tests evaluate against real backend state.
	const odyssey::presentation::LightRule Own = ToNative(OwnLightRule);
	odyssey::presentation::LightRule Warning;
	Warning.warning = true;
	TArray<odyssey::presentation::LightRule> Groups;
	for (const FOdysseyLightGroup& G : LightGroups)
	{
		Groups.Add(ToNative(G.Rule));
	}
	GroupScale.Reset();
	for (int32 G = 0; G < LightGroups.Num(); ++G)
	{
		GroupScale.Add(LightGroups[G].Name, static_cast<float>(odyssey::presentation::EvaluateIn(Groups[G], *M, Id)));
	}
	for (FLightState& L : Lights)
	{
		if (!L.Light.IsValid()) continue;
		const odyssey::presentation::LightRule& Rule = L.Group != INDEX_NONE ? Groups[L.Group] : (L.bOwnWarning ? Warning : Own);
		L.From = L.Light->Intensity / FMath::Max(L.BaseIntensity, KINDA_SMALL_NUMBER);
		L.To = static_cast<float>(odyssey::presentation::EvaluateIn(Rule, *M, Id));
	}
	BlendAlpha = 0.f;
	SetComponentTickEnabled(true);
	Current = B->GetObjectView(GetObjectId());
	OnObjectStateChanged(Current, odyssey::presentation::IncidentInvolves(*M, Id));
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
