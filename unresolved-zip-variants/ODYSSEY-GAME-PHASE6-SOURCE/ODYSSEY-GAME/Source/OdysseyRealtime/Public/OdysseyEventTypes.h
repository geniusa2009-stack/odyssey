// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Typed realtime events. Every event has ALREADY been applied to the local semantic mirror when it
// is routed; payloads carry identity and the facts the event states, and presentation reads the
// current values from the mirror (UOdysseyBackendSubsystem::Get*View). Raw JSON never reaches actors.
#pragma once

#include "CoreMinimal.h"

#include "OdysseyEventTypes.generated.h"

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyEventMeta
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Type;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Scope;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") int64 Seq = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") int64 StateVersion = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") int64 SimTick = 0;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseySystemStateEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName ObjectId;
	// Fields the backend says changed (status, power, mode, access, inspected, infrastructure_state…)
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") TArray<FName> ChangedFields;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyIncidentEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName IncidentId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Stage;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") bool bResolved = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") TArray<FName> InvolvedObjects;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") TArray<FName> InvolvedCrew;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyAccessEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName SemanticId;  // location or object
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Access;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyInventoryEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName ContainerId;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyObjectiveEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName ObjectiveId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Status;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyAlertEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName AlertId;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") bool bActive = false;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Severity;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Category;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyMissionEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Status;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName SimulationStatus;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyClockEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Mode;  // PAUSED REALTIME ACCELERATED DECISION_PAUSED
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName PauseReason;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") float TicksPerSecond = 0.f;
};

USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyCrewEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName CrewId;
};

// crew.cue: a short authored line (also the ORION presentation feed). Text is backend content.
USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyCueEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Cue;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Speaker;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FString Line;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName MessageKey;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") int32 Priority = 0;
};

// capability.progressed / certification.granted / discovery.recorded / knowledge.unlocked
USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyProgressEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Id;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName Stage;
};

// future_lens.ready / black_box.ready / checkpoint.saved (notifications; data is fetched on demand)
USTRUCT(BlueprintType)
struct ODYSSEYREALTIME_API FOdysseyInfoEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FOdysseyEventMeta Meta;
	UPROPERTY(BlueprintReadOnly, Category = "Odyssey|Event") FName TimelineId;
};
