









#pragma once

#include "CoreMinimal.h"
#include "Containers/Ticker.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "OdysseyBackendSettings.h"
#include "OdysseyBackendTypes.h"

#include "OdysseyProtocol/SessionMachine.h"

#include <memory>

#include "OdysseyBackendSubsystem.generated.h"

class FOdysseyRealtimeConnection;
class UOdysseyEventRouter;
class UOdysseySemanticRegistry;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseySessionStateSignature, EOdysseySessionState, State);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOdysseySessionReadySignature);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyCommandResolvedSignature, const FOdysseyCommandResolution&, Resolution);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyRestoreSignature, const FOdysseyRestoreSummary&, Summary);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyReasonSignature, const FString&, Reason);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyUnknownIdsSignature, const TArray<FName>&, Ids);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyFutureLensSignature, const FOdysseyFutureLensView&, View);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOdysseyBlackBoxSignature, const FOdysseyBlackBoxView&, View);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOdysseyMirrorVerifiedSignature, int32, DifferenceCount, const FString&, FirstDifference);

UCLASS()
class ODYSSEYBACKEND_API UOdysseyBackendSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	static UOdysseyBackendSubsystem* Get(const UObject* WorldContext);

	
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	void StartSession();

	
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	void ForgetStoredSession();

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	void RequestRestore();

	
	
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	int64 SubmitIntent(const FOdysseySemanticIntent& Intent);

	
	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	void RequestFutureLens(const TArray<FOdysseySemanticIntent>& Candidates, int32 HorizonTicks = 12);

	UFUNCTION(BlueprintCallable, Category = "Odyssey|Backend")
	void RequestBlackBox(const FString& TimelineId, bool bCounterfactuals = false);

	
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") EOdysseySessionState GetSessionState() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") bool IsSessionReady() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyMissionContext GetMissionContext() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FName GetPlayerSemanticLocation() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyObjectView GetObjectView(FName ObjectId) const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyLocationView GetLocationView(FName LocationId) const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyContainerView GetContainerView(FName ContainerId) const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyCrewView GetCrewView(FName CrewId) const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") TArray<FOdysseyIncidentView> GetIncidents(bool bActiveOnly = true) const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") TArray<FOdysseyObjectiveView> GetObjectives() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") TArray<FOdysseyResourceView> GetResources() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyAuthorizationView GetAuthorization() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") TArray<FName> GetCertifications() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") FOdysseyConnectionStatus GetConnectionStatus() const;
	UFUNCTION(BlueprintPure, Category = "Odyssey|State") UOdysseyEventRouter* GetEventRouter() const { return Router; }

	const odyssey::MirrorModel* GetMirrorModel() const;

	
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseySessionStateSignature OnSessionStateChanged;
	
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseySessionReadySignature OnSessionReady;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyCommandResolvedSignature OnCommandResolved;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyRestoreSignature OnRestored;
	
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyReasonSignature OnSessionReplaced;
	
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyReasonSignature OnSessionInvalid;
	
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyReasonSignature OnProtocolMismatch;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyReasonSignature OnBackendError;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyUnknownIdsSignature OnUnknownSemanticIds;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyFutureLensSignature OnFutureLensReady;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyBlackBoxSignature OnBlackBoxReady;
	UPROPERTY(BlueprintAssignable, Category = "Odyssey|Backend") FOdysseyMirrorVerifiedSignature OnMirrorVerified;

#if !UE_BUILD_SHIPPING
	
	void DebugLoseNextCommandResponses(int32 Count) { DebugLoseResponses = FMath::Max(0, Count); }
	void DebugDropRealtime();
	void DebugSetScrambleRealtime(bool bEnabled);
	void DebugForceStaleNextCommand();
	
	void DebugVerifyMirror();
#endif

private:
	bool Tick(float DeltaTime);
	void Execute(odyssey::Effects&& Fx);
	void ExecuteHttp(const odyssey::HttpEffect& Http, uint32 Generation);
	void ConnectRealtime(const FString& Path);
	void HandleNotice(const odyssey::Notice& N);
	void PersistCredentials();
	odyssey::Credentials LoadCredentials() const;
	FString SaveSlotName() const;
	void ReportUnknownIds();
	static std::string NewUuid();

	std::unique_ptr<odyssey::SessionMachine> Machine;
	TSharedPtr<FOdysseyRealtimeConnection> Realtime;
	FTSTicker::FDelegateHandle TickerHandle;
	TMap<FString, double> Timers;  
	TMap<int64, FOdysseySemanticIntent> IntentsInFlight;
	TSet<FName> ReportedUnknown;
	FOdysseyBackendEnvironment Env;
	FName EnvName;
	FString LastError;
	uint32 SessionGeneration = 0;  
	bool bReadyBroadcast = false;
	int32 DebugLoseResponses = 0;

	UPROPERTY() TObjectPtr<UOdysseyEventRouter> Router;
	UPROPERTY() TObjectPtr<UOdysseySemanticRegistry> Registry;
};
