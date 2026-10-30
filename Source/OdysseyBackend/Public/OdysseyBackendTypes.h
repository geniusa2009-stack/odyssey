// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Blueprint-facing views of the local semantic mirror and of command/analysis results. They are
// copies taken on request from odyssey::MirrorModel; nothing here is authoritative.
#pragma once

#include "CoreMinimal.h"

#include "OdysseyBackendTypes.generated.h"

UENUM(BlueprintType)
enum class EOdysseySessionState : uint8
{
	Idle,
	CheckingReady,
	LoadingFeatures,
	Restoring,
	CreatingSession,
	ConnectingRealtime,
	Ready,
	Recovering,
	Failed,
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyIntentParam
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") FName Name;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") FString StringValue;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") bool bIsInteger = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") int64 IntegerValue = 0;
};

// What the player wants to do, in backend terms. Never positions, never results.
USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseySemanticIntent
{
	GENERATED_BODY()
	// e.g. system.inspect, repair.perform, system.set_mode, power.reroute, world.zone_entered
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") FName Action;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") FName Target;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") TArray<FOdysseyIntentParam> Params;
	// Optional Unreal anchor name (diagnostics only; the backend does not interpret it).
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") FName Anchor;
	// Re-submit once after STALE_STATE if the refreshed state still offers the action.
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey") bool bResubmitAfterStale = true;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyInteractionView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Action;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bAvailable = false;
	// Safe backend reason when unavailable (e.g. not_at_location, fault_not_diagnosed).
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Reason;
	// Allowed values per parameter, as offered by the backend.
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TMap<FName, FString> ParamChoices;  // name -> comma-separated values
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyObjectView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bFound = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Kind;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString DisplayName;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Location;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Status;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Access;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Power;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Mode;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName InfrastructureState;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bInspected = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bCritical = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bHasCharge = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") float ChargeKwh = 0.f;
	// True between interactions.changed and the backend refresh: show "updating", not stale choices.
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bInteractionsRefreshing = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyInteractionView> Interactions;
	// Active incidents that involve this object.
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> ActiveIncidents;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyLocationView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bFound = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString DisplayName;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Access;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bVisited = false;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyIncidentView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Stage;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName MessageKey;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bResolved = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> InvolvedObjects;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> InvolvedCrew;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyObjectiveView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Status;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName MessageKey;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bRequired = false;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyResourceView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString Label;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString Unit;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") float Value = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName WarningState;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyCrewView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bFound = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString DisplayName;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString Role;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Intent;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Location;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName HealthBand;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> InvolvedIncidents;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyRequirementView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bMet = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Reason;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyAuthorizationView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bPresent = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Gate;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Target;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bAvailable = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bAuthorized = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyRequirementView> Requirements;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyContainerItemView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Item;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 Quantity = 0;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyContainerView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bFound = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") float MassKg = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyContainerItemView> Items;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyMissionContext
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName MissionId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString MissionTitle;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName MissionStatus;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ActivePhase;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName PlayerLocation;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ClockMode;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName PauseReason;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 SimTick = 0;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyCommandResolution
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 LocalId = 0;
	// applied, no_change, stale, rejected, mission_complete, session_invalid, client_bug,
	// superseded (stale and no longer offered), rejected_locally
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Outcome;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Action;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Target;
	// Backend error code/reason when rejected (safe to show, e.g. DECISION_UNAVAILABLE / not_at_location).
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ErrorCode;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Reason;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 StateVersion = 0;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyRestoreSummary
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 TicksAdvanced = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> EventTypes;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyLensBranchView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Action;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Target;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bBaseline = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bValid = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName RejectionReason;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ProjectedOutcomeTier;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ConfidenceLevel;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") float RiskPeak = 0.f;
	// "object.field: now → after" lines for the debug view.
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FString> WorldHints;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FName> Warnings;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyFutureLensView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bOk = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName PredictionMode;  // known_only: never foresees hidden events
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 BaseTick = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") float HorizonHours = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyLensBranchView> Branches;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyCausalNodeView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Type;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString Label;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Severity;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 SimTick = -1;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyCausalEdgeView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Source;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Target;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Relation;
};

USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyBlackBoxView
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") bool bOk = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName TimelineId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName MissionId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName OutcomeTier;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString Statement;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyCausalNodeView> Nodes;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") TArray<FOdysseyCausalEdgeView> Edges;
};

// Everything the development overlay shows.
USTRUCT(BlueprintType)
struct ODYSSEYBACKEND_API FOdysseyConnectionStatus
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName Environment;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString ServerRoot;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") EOdysseySessionState State = EOdysseySessionState::Idle;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString SessionId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString TimelineId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 StateVersion = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int64 LastSeq = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName SemanticLocation;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString LastCommand;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString RealtimeState;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int32 ReconnectAttempts = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int32 QueuedIntents = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") int32 DuplicatesDropped = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ActiveIncident;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FName ClockMode;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey") FString LastError;
};
