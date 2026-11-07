
#include "OdysseyInteractableComponent.h"

#include "GameFramework/Actor.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseySemanticBindingComponent.h"

UOdysseyInteractableComponent::UOdysseyInteractableComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

TArray<FName> UOdysseyInteractableComponent::GetSemanticIdOptions()
{
	return UOdysseySemanticBindingComponent::GetSemanticIdOptions();
}

FName UOdysseyInteractableComponent::GetTargetId() const
{
	if (!SemanticTargetId.IsNone())
	{
		return SemanticTargetId;
	}
	const UOdysseySemanticBindingComponent* B = GetOwner()->FindComponentByClass<UOdysseySemanticBindingComponent>();
	return B ? B->SemanticId : NAME_None;
}

void UOdysseyInteractableComponent::BeginPlay()
{
	Super::BeginPlay();
	if (UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this))
	{
		S->OnCommandResolved.AddDynamic(this, &UOdysseyInteractableComponent::HandleResolved);
		S->OnSessionStateChanged.AddDynamic(this, &UOdysseyInteractableComponent::HandleSessionState);
		if (UOdysseyEventRouter* R = S->GetEventRouter())
		{
			R->OnInteractionsRefreshed.AddDynamic(this, &UOdysseyInteractableComponent::HandleRefreshed);
			R->OnSystemStateChanged.AddDynamic(this, &UOdysseyInteractableComponent::HandleSystem);
			R->OnSnapshotApplied.AddDynamic(this, &UOdysseyInteractableComponent::HandleSnapshot);
		}
	}
}

TArray<FOdysseyInteractionView> UOdysseyInteractableComponent::GetOfferedActions() const
{
	TArray<FOdysseyInteractionView> Out;
	const UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	if (!S)
	{
		return Out;
	}
	const FOdysseyObjectView View = S->GetObjectView(GetTargetId());
	for (const FOdysseyInteractionView& I : View.Interactions)
	{
		if (PresentedActions.Num() == 0 || PresentedActions.Contains(I.Action))
		{
			Out.Add(I);
		}
	}
	return Out;
}

int64 UOdysseyInteractableComponent::RequestAction(FName Action, const TArray<FOdysseyIntentParam>& Params)
{
	UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	if (!S || !S->IsSessionReady())
	{
		return 0;
	}
	FOdysseySemanticIntent Intent;
	Intent.Action = Action;
	Intent.Target = GetTargetId();
	Intent.Params = Params;
	Intent.Anchor = GetOwner()->GetFName();
	
	
	const int64 Id = S->SubmitIntent(Intent);
	if (Id != 0)
	{
		Pending.Add(Id);
		UpdatePrompt();
	}
	return Id;
}

void UOdysseyInteractableComponent::SetFocused(bool bFocused)
{
	if (bIsFocused != bFocused)
	{
		bIsFocused = bFocused;
		OnFocusChanged.Broadcast(bFocused);
		UpdatePrompt();
	}
}

void UOdysseyInteractableComponent::Activate()
{
	OnActivatedEvent.Broadcast();
	OnActivated();
}

void UOdysseyInteractableComponent::HandleResolved(const FOdysseyCommandResolution& R)
{
	if (!Pending.Contains(R.LocalId) || R.Outcome == TEXT("stale"))
	{
		return;  
	}
	Pending.Remove(R.LocalId);
	OnActionResolved.Broadcast(R);
	UpdatePrompt();
}

void UOdysseyInteractableComponent::HandleRefreshed(FName ObjectId)
{
	if (ObjectId == GetTargetId()) UpdatePrompt();
}

void UOdysseyInteractableComponent::HandleSystem(const FOdysseySystemStateEvent& E)
{
	if (E.ObjectId == GetTargetId()) UpdatePrompt();
}

void UOdysseyInteractableComponent::HandleSnapshot(FName)
{
	UpdatePrompt();
}

void UOdysseyInteractableComponent::HandleSessionState(EOdysseySessionState)
{
	UpdatePrompt();
}

void UOdysseyInteractableComponent::UpdatePrompt()
{
	EOdysseyPromptState Next = EOdysseyPromptState::Hidden;
	const UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	if (bIsFocused)
	{
		if (!S || !S->IsSessionReady())
		{
			Next = EOdysseyPromptState::Offline;
		}
		else if (Pending.Num() > 0)
		{
			Next = EOdysseyPromptState::Pending;
		}
		else if (S->GetObjectView(GetTargetId()).bInteractionsRefreshing)
		{
			Next = EOdysseyPromptState::Refreshing;
		}
		else
		{
			Next = EOdysseyPromptState::Unavailable;
			for (const FOdysseyInteractionView& I : GetOfferedActions())
			{
				if (I.bAvailable)
				{
					Next = EOdysseyPromptState::Available;
					break;
				}
			}
		}
	}
	if (Next != PromptState)
	{
		PromptState = Next;
		OnPromptStateChanged.Broadcast(Next);
	}
}
