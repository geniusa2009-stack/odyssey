
#include "OdysseyCrewPlaceholder.h"

#include "Components/StateTreeComponent.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseySemanticBindingComponent.h"

AOdysseyCrewPlaceholder::AOdysseyCrewPlaceholder()
{
	Binding = CreateDefaultSubobject<UOdysseySemanticBindingComponent>(TEXT("SemanticBinding"));
	CrewState = CreateDefaultSubobject<UOdysseyCrewStateComponent>(TEXT("CrewState"));
	StateTree = CreateDefaultSubobject<UStateTreeComponent>(TEXT("StateTree"));
	StateTree->SetStartLogicAutomatically(true);
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
}

void UOdysseyCrewStateComponent::BeginPlay()
{
	Super::BeginPlay();
	if (const UOdysseySemanticBindingComponent* B = GetOwner()->FindComponentByClass<UOdysseySemanticBindingComponent>())
	{
		CrewId = B->SemanticId;
	}
	if (UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this))
	{
		if (UOdysseyEventRouter* R = S->GetEventRouter())
		{
			R->OnCrewUpdated.AddDynamic(this, &UOdysseyCrewStateComponent::HandleCrew);
			R->OnCrewCue.AddDynamic(this, &UOdysseyCrewStateComponent::HandleCue);
			R->OnSnapshotApplied.AddDynamic(this, &UOdysseyCrewStateComponent::HandleSnapshot);
			R->OnIncident.AddDynamic(this, &UOdysseyCrewStateComponent::HandleIncident);
		}
	}
	Refresh();
}

AActor* UOdysseyCrewStateComponent::GetCurrentLocationPoint() const
{
	const TObjectPtr<AActor>* P = LocationPoints.Find(SemanticLocation);
	return P ? P->Get() : nullptr;
}

void UOdysseyCrewStateComponent::HandleCrew(const FOdysseyCrewEvent& E)
{
	if (E.CrewId == CrewId) Refresh();
}

void UOdysseyCrewStateComponent::HandleCue(const FOdysseyCueEvent& E)
{
	if (E.Speaker == CrewId)
	{
		LastCueLine = E.Line;
		OnCue(E);
	}
}

void UOdysseyCrewStateComponent::HandleSnapshot(FName)
{
	Refresh();
}

void UOdysseyCrewStateComponent::HandleIncident(const FOdysseyIncidentEvent& E)
{
	if (E.InvolvedCrew.Contains(CrewId)) Refresh();
}

void UOdysseyCrewStateComponent::Refresh()
{
	const UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	if (!S)
	{
		return;
	}
	const FOdysseyCrewView V = S->GetCrewView(CrewId);
	if (!V.bFound)
	{
		return;
	}
	Intent = V.Intent;
	SemanticLocation = V.Location;
	HealthBand = V.HealthBand;
	bIncidentActive = false;
	for (const FOdysseyIncidentView& I : S->GetIncidents(true))
	{
		bIncidentActive = bIncidentActive || V.InvolvedIncidents.Contains(I.Id);
	}
	OnCrewStateChanged();
}
