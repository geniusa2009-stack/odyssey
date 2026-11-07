
#include "OdysseyOrionPresenter.h"

#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"

void UOdysseyOrionPresenter::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UOdysseyBackendSubsystem* B = Collection.InitializeDependency<UOdysseyBackendSubsystem>();
	if (B && B->GetEventRouter())
	{
		B->GetEventRouter()->OnCrewCue.AddDynamic(this, &UOdysseyOrionPresenter::HandleCue);
	}
}

void UOdysseyOrionPresenter::HandleCue(const FOdysseyCueEvent& Cue)
{
	FOdysseyOrionLine L;
	L.Speaker = Cue.Speaker;
	L.Text = Cue.Line;
	L.MessageKey = Cue.MessageKey;
	L.Priority = Cue.Priority;
	L.SimTick = Cue.Meta.SimTick;
	L.Source = TEXT("crew.cue");
	Recent.Add(L);
	if (Recent.Num() > MaxRecent)
	{
		Recent.RemoveAt(0, Recent.Num() - MaxRecent);
	}
	OnLine.Broadcast(L);
}
