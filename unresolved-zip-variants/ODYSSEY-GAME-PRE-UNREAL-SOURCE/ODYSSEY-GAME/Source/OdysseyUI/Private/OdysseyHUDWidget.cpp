// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyHUDWidget.h"

#include "Components/TextBlock.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseyInteractableComponent.h"
#include "OdysseyInteractorComponent.h"

void UOdysseyHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();
	if (UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this))
	{
		B->OnSessionStateChanged.AddDynamic(this, &UOdysseyHUDWidget::HandleState);
		if (UOdysseyEventRouter* R = B->GetEventRouter())
		{
			R->OnSnapshotApplied.AddDynamic(this, &UOdysseyHUDWidget::HandleSnapshot);
			R->OnIncident.AddDynamic(this, &UOdysseyHUDWidget::HandleIncident);
			R->OnClockUpdated.AddDynamic(this, &UOdysseyHUDWidget::HandleClock);
			R->OnObjectiveUpdated.AddDynamic(this, &UOdysseyHUDWidget::HandleObjective);
		}
	}
	Refresh();
}

void UOdysseyHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);
	SincePromptCheck += InDeltaTime;
	if (SincePromptCheck > 0.1f && InteractionPrompt)
	{
		SincePromptCheck = 0.f;
		InteractionPrompt->SetText(PromptText());
	}
}

FText UOdysseyHUDWidget::PromptText() const
{
	const APlayerController* PC = GetOwningPlayer();
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const UOdysseyInteractorComponent* I = Pawn ? Pawn->FindComponentByClass<UOdysseyInteractorComponent>() : nullptr;
	const UOdysseyInteractableComponent* F = I ? I->GetFocused() : nullptr;
	if (!F)
	{
		return FText::GetEmpty();
	}
	switch (F->GetPromptState())
	{
	case EOdysseyPromptState::Offline: return NSLOCTEXT("Odyssey", "PromptOffline", "Station link offline");
	case EOdysseyPromptState::Pending: return NSLOCTEXT("Odyssey", "PromptPending", "…");
	case EOdysseyPromptState::Refreshing: return NSLOCTEXT("Odyssey", "PromptRefreshing", "Updating");
	default: return F->PromptText;
	}
}

void UOdysseyHUDWidget::Refresh_Implementation()
{
	const UOdysseyBackendSubsystem* B = UOdysseyBackendSubsystem::Get(this);
	if (!B)
	{
		return;
	}
	const bool bReady = B->IsSessionReady();
	if (ConnectionState)
	{
		const EOdysseySessionState S = B->GetSessionState();
		ConnectionState->SetText(bReady ? FText::GetEmpty()
			: S == EOdysseySessionState::Recovering ? NSLOCTEXT("Odyssey", "Reconnecting", "Re-establishing station link")
			: S == EOdysseySessionState::Failed ? NSLOCTEXT("Odyssey", "LinkFailed", "Station link unavailable")
												: NSLOCTEXT("Odyssey", "Connecting", "Connecting to ODYSSEY"));
	}
	const FOdysseyMissionContext M = B->GetMissionContext();
	if (MissionContext)
	{
		MissionContext->SetText(bReady ? FText::FromString(M.MissionTitle) : FText::GetEmpty());
	}
	if (CriticalWarning)
	{
		// One line only: the incident is presented in the world; this is the minimal global cue.
		const TArray<FOdysseyIncidentView> Active = B->GetIncidents(true);
		CriticalWarning->SetText(Active.Num() > 0 && M.ClockMode == TEXT("DECISION_PAUSED")
			? NSLOCTEXT("Odyssey", "DecisionPaused", "Station alert — time held for your decision")
			: Active.Num() > 0 ? NSLOCTEXT("Odyssey", "StationAlert", "Station alert") : FText::GetEmpty());
	}
	if (ObjectiveCue)
	{
		FText Cue = FText::GetEmpty();
		for (const FOdysseyObjectiveView& O : B->GetObjectives())
		{
			if (O.bRequired && O.Status == TEXT("pending"))  // backend status values: pending, then its outcome
			{
				// message keys are localized via the string table ST_Objectives (content)
				Cue = FText::FromName(O.MessageKey);
				break;
			}
		}
		ObjectiveCue->SetText(Cue);
	}
}

void UOdysseyHUDWidget::HandleState(EOdysseySessionState) { Refresh(); }
void UOdysseyHUDWidget::HandleSnapshot(FName) { Refresh(); }
void UOdysseyHUDWidget::HandleIncident(const FOdysseyIncidentEvent&) { Refresh(); }
void UOdysseyHUDWidget::HandleClock(const FOdysseyClockEvent&) { Refresh(); }
void UOdysseyHUDWidget::HandleObjective(const FOdysseyObjectiveEvent&) { Refresh(); }
