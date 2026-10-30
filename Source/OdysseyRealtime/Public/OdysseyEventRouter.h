// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Typed event router. Fed by UOdysseyBackendSubsystem with the session machine's notices, AFTER
// the mirror has applied the event. Unknown event types are counted and ignored (forward
// compatible); presentation never parses JSON.
#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "OdysseyEventTypes.h"

#include "OdysseyProtocol/SessionMachine.h"

#include "OdysseyEventRouter.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseySystemStateSignature, const FOdysseySystemStateEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyIncidentSignature, const FOdysseyIncidentEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyAccessSignature, const FOdysseyAccessEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyInventorySignature, const FOdysseyInventoryEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyObjectiveSignature, const FOdysseyObjectiveEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyAlertSignature, const FOdysseyAlertEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyMissionSignature, const FOdysseyMissionEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyClockSignature, const FOdysseyClockEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyCrewSignature, const FOdysseyCrewEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyCueSignature, const FOdysseyCueEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyProgressSignature, const FOdysseyProgressEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyInfoSignature, const FOdysseyInfoEvent&, Event);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyIdsChangedSignature, const TArray<FName>&, SemanticIds);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseySnapshotSignature, FName, Reason);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyObjectSignature, FName, ObjectId);

UCLASS(BlueprintType)
class ODYSSEYREALTIME_API UOdysseyEventRouter : public UObject
{
	GENERATED_BODY()

public:
	// system.state_changed, infrastructure.changed
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseySystemStateSignature OnSystemStateChanged;
	// incident.started / incident.updated / incident.resolved
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyIncidentSignature OnIncident;
	// world.access_changed
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyAccessSignature OnAccessChanged;
	// inventory.changed / cargo.changed
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyInventorySignature OnInventoryChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyObjectiveSignature OnObjectiveUpdated;
	// resource.threshold_changed / system.alert_changed
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyAlertSignature OnAlertChanged;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyMissionSignature OnMissionUpdated;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyClockSignature OnClockUpdated;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyCrewSignature OnCrewUpdated;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyCueSignature OnCrewCue;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyProgressSignature OnCapabilityProgressed;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyProgressSignature OnCertificationGranted;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyProgressSignature OnKnowledge;  // discovery / insight
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyInfoSignature OnFutureLensReady;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyInfoSignature OnBlackBoxReady;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyInfoSignature OnCheckpointSaved;
	// Interaction availability for an object was refreshed from the backend (GET /objects/{id}).
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyObjectSignature OnInteractionsRefreshed;
	// Generic: these semantic ids changed (any event). Cheap hook for bound actors.
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseyIdsChangedSignature OnSemanticIdsChanged;
	// The whole mirror was replaced (bootstrap, restore, stale refresh, transition…): re-read everything.
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Events") FOdysseySnapshotSignature OnSnapshotApplied;

	void Route(const odyssey::Notice& Notice);

	UFUNCTION(BlueprintPure, Category = "Odyssey|Events") int32 GetRoutedCount() const { return Routed; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Events") int32 GetUnroutedCount() const { return Unrouted; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Events") int64 GetLastSeq() const { return LastSeq; }
	UFUNCTION(BlueprintPure, Category = "Odyssey|Events") FName GetLastType() const { return LastType; }

	// Exposed for automation tests (fixture envelope → typed struct).
	static FOdysseyEventMeta MetaFrom(const odyssey::json::Value& Envelope);

private:
	void RouteEvent(const std::string& Type, const odyssey::json::Value& Env, const std::vector<std::string>& Ids);

	int32 Routed = 0;
	int32 Unrouted = 0;
	int64 LastSeq = 0;
	FName LastType;
};
