// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyPowerConsole.h"

#include "Components/StaticMeshComponent.h"
#include "Components/WidgetComponent.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyEventRouter.h"
#include "OdysseyInteractableComponent.h"
#include "OdysseyObjectPresentationComponent.h"
#include "OdysseySemanticBindingComponent.h"

AOdysseyPowerConsole::AOdysseyPowerConsole()
{
	PrimaryActorTick.bCanEverTick = false;
	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	RootComponent = Body;
	Display = CreateDefaultSubobject<UWidgetComponent>(TEXT("Display"));
	Display->SetupAttachment(Body);
	Display->SetWidgetSpace(EWidgetSpace::World);
	Display->SetDrawSize(FVector2D(640.f, 400.f));
	Binding = CreateDefaultSubobject<UOdysseySemanticBindingComponent>(TEXT("SemanticBinding"));
	Binding->SemanticId = TEXT("earth.command.engineering.power_bus_b");
	Interactable = CreateDefaultSubobject<UOdysseyInteractableComponent>(TEXT("Interactable"));
	Interactable->PromptText = NSLOCTEXT("Odyssey", "PowerConsolePrompt", "Power distribution");
	Presentation = CreateDefaultSubobject<UOdysseyObjectPresentationComponent>(TEXT("Presentation"));

	// Default physical controls for the slice (labels are engravings, not hints).
	FOdysseyConsoleControl Inspect;
	Inspect.Action = TEXT("system.inspect");
	Inspect.Label = NSLOCTEXT("Odyssey", "CtlInspect", "DIAGNOSTIC");
	Controls.Add(Inspect);
	FOdysseyConsoleControl Repair;
	Repair.Action = TEXT("repair.perform");
	Repair.Label = NSLOCTEXT("Odyssey", "CtlRepair", "BREAKER SERVICE");
	Controls.Add(Repair);
}

void AOdysseyPowerConsole::BeginPlay()
{
	Super::BeginPlay();
	Interactable->OnActivatedEvent.AddDynamic(this, &AOdysseyPowerConsole::HandleActivated);
	Interactable->OnFocusChanged.AddDynamic(this, &AOdysseyPowerConsole::HandleFocus);
	if (UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this))
	{
		S->OnCommandResolved.AddDynamic(this, &AOdysseyPowerConsole::HandleResolved);
		if (UOdysseyEventRouter* R = S->GetEventRouter())
		{
			R->OnInteractionsRefreshed.AddDynamic(this, &AOdysseyPowerConsole::HandleAnyChange);
			R->OnSnapshotApplied.AddDynamic(this, &AOdysseyPowerConsole::HandleSnapshot);
		}
	}
	PublishControls();
}

TArray<FOdysseyConsoleControlState> AOdysseyPowerConsole::GetControlStates() const
{
	TArray<FOdysseyConsoleControlState> Out;
	const UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	for (const FOdysseyConsoleControl& C : Controls)
	{
		FOdysseyConsoleControlState St;
		St.Control = C;
		if (S)
		{
			const FName Target = C.TargetOverride.IsNone() ? Interactable->GetTargetId() : C.TargetOverride;
			for (const FOdysseyInteractionView& I : S->GetObjectView(Target).Interactions)
			{
				if (I.Action == C.Action)
				{
					St.bOffered = true;
					St.bAvailable = I.bAvailable;
					St.Reason = I.Reason;
				}
			}
		}
		Out.Add(St);
	}
	return Out;
}

int64 AOdysseyPowerConsole::PressControl(int32 Index)
{
	UOdysseyBackendSubsystem* S = UOdysseyBackendSubsystem::Get(this);
	if (!bPanelActive || !Controls.IsValidIndex(Index) || !S || !S->IsSessionReady())
	{
		return 0;
	}
	const FOdysseyConsoleControl& C = Controls[Index];
	FOdysseySemanticIntent Intent;
	Intent.Action = C.Action;
	Intent.Target = C.TargetOverride.IsNone() ? Interactable->GetTargetId() : C.TargetOverride;
	Intent.Params = C.Params;
	Intent.Anchor = GetFName();
	const int64 Id = S->SubmitIntent(Intent);
	if (Id != 0)
	{
		PendingControls.Add(Id, Index);
	}
	return Id;
}

void AOdysseyPowerConsole::SetPanelActive(bool bActive)
{
	if (bPanelActive != bActive)
	{
		bPanelActive = bActive;
		OnPanelActiveChanged(bActive);
		PublishControls();
	}
}

void AOdysseyPowerConsole::HandleActivated()
{
	SetPanelActive(true);
}

void AOdysseyPowerConsole::HandleFocus(bool bFocused)
{
	if (!bFocused)
	{
		SetPanelActive(false);  // walking away closes the panel
	}
}

void AOdysseyPowerConsole::HandleResolved(const FOdysseyCommandResolution& R)
{
	const int32* Index = PendingControls.Find(R.LocalId);
	if (!Index || R.Outcome == TEXT("stale"))
	{
		return;
	}
	const int32 I = *Index;
	PendingControls.Remove(R.LocalId);
	OnControlResolved(I, R);
	PublishControls();
}

void AOdysseyPowerConsole::HandleAnyChange(FName)
{
	PublishControls();
}

void AOdysseyPowerConsole::HandleSnapshot(FName)
{
	PublishControls();
}

void AOdysseyPowerConsole::PublishControls()
{
	OnControlsChanged(GetControlStates());
}
