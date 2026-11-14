// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled or run inside Unreal Engine 5.8.
// The protocol behaviour it executes (odyssey::SessionMachine) is verified natively: fixture tests
// (Tools/ProtocolCore, 26 cases) and the live harness against the real backend (run_live.sh).
#include "OdysseyBackendSubsystem.h"

#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/Guid.h"
#include "OdysseyCore.h"
#include "OdysseyEventRouter.h"
#include "OdysseyRealtimeConnection.h"
#include "OdysseySemanticRegistry.h"
#include "OdysseySessionSaveGame.h"
#include "OdysseyStringConv.h"

#include "OdysseyProtocol/MirrorDiff.h"

#include <array>

using namespace OdysseyConv;

namespace
{
EOdysseySessionState ToUE(odyssey::SessionState S)
{
	switch (S)
	{
	case odyssey::SessionState::Idle: return EOdysseySessionState::Idle;
	case odyssey::SessionState::CheckingReady: return EOdysseySessionState::CheckingReady;
	case odyssey::SessionState::LoadingFeatures: return EOdysseySessionState::LoadingFeatures;
	case odyssey::SessionState::Restoring: return EOdysseySessionState::Restoring;
	case odyssey::SessionState::CreatingSession: return EOdysseySessionState::CreatingSession;
	case odyssey::SessionState::ConnectingRealtime: return EOdysseySessionState::ConnectingRealtime;
	case odyssey::SessionState::Ready: return EOdysseySessionState::Ready;
	case odyssey::SessionState::Recovering: return EOdysseySessionState::Recovering;
	case odyssey::SessionState::Failed: return EOdysseySessionState::Failed;
	}
	return EOdysseySessionState::Failed;
}

odyssey::SemanticIntent ToNative(const FOdysseySemanticIntent& In)
{
	odyssey::SemanticIntent Out;
	Out.action = ToStd(In.Action);
	Out.target = ToStd(In.Target);
	Out.anchor = ToStd(In.Anchor);
	Out.resubmitAfterStale = In.bResubmitAfterStale;
	for (const FOdysseyIntentParam& P : In.Params)
	{
		Out.params.emplace_back(ToStd(P.Name),
			P.bIsInteger ? odyssey::ParamValue::Int(P.IntegerValue) : odyssey::ParamValue::Str(ToStd(P.StringValue)));
	}
	return Out;
}

TArray<FName> ToNames(const std::vector<std::string>& V)
{
	TArray<FName> Out;
	for (const std::string& S : V)
	{
		Out.Add(ToFName(S));
	}
	return Out;
}

FOdysseyObjectView ToView(const odyssey::ObjectInfo& O, const odyssey::MirrorModel& M)
{
	FOdysseyObjectView V;
	V.bFound = true;
	V.Id = ToFName(O.id);
	V.Kind = ToFName(O.kind);
	V.DisplayName = ToFString(O.name);
	V.Location = ToFName(O.location);
	V.Status = ToFName(O.status);
	V.Access = ToFName(O.access);
	V.Power = ToFName(O.power);
	V.Mode = ToFName(O.mode);
	V.InfrastructureState = ToFName(O.infrastructureState);
	V.bInspected = O.inspected;
	V.bCritical = O.critical;
	V.bHasCharge = O.hasCharge;
	V.ChargeKwh = static_cast<float>(O.chargeKwh);
	V.bInteractionsRefreshing = O.interactionsStale;
	for (const odyssey::InteractionInfo& I : O.interactions)
	{
		FOdysseyInteractionView IV;
		IV.Action = ToFName(I.action);
		IV.bAvailable = I.available;
		IV.Reason = ToFName(I.reason);
		for (const auto& P : I.params)
		{
			FString Joined;
			for (const std::string& Choice : P.second)
			{
				Joined += (Joined.IsEmpty() ? TEXT("") : TEXT(",")) + ToFString(Choice);
			}
			IV.ParamChoices.Add(ToFName(P.first), Joined);
		}
		V.Interactions.Add(IV);
	}
	for (const odyssey::IncidentInfo* Inc : M.activeIncidents())
	{
		if (std::find(Inc->involvedObjects.begin(), Inc->involvedObjects.end(), O.id) != Inc->involvedObjects.end())
		{
			V.ActiveIncidents.Add(ToFName(Inc->id));
		}
	}
	return V;
}
}  // namespace

// ================================================================ lifecycle
void UOdysseyBackendSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	Registry = Collection.InitializeDependency<UOdysseySemanticRegistry>();
	Router = NewObject<UOdysseyEventRouter>(this);
	if (GetDefault<UOdysseyBackendSettings>()->IsAndroidJudgeOffline())
	{
		return; // No HTTP, WebSocket, credentials or retries in the isolated Android exploration build.
	}
	TickerHandle = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UOdysseyBackendSubsystem::Tick), 0.0f);
	if (GetDefault<UOdysseyBackendSettings>()->bAutoStartSession)
	{
		StartSession();
	}
}

void UOdysseyBackendSubsystem::Deinitialize()
{
	FTSTicker::GetCoreTicker().RemoveTicker(TickerHandle);
	++SessionGeneration;
	if (Machine)
	{
		Execute(Machine->Shutdown());
	}
	if (Realtime)
	{
		Realtime->Close();
		Realtime.Reset();
	}
	Machine.reset();
	Super::Deinitialize();
}

UOdysseyBackendSubsystem* UOdysseyBackendSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UOdysseyBackendSubsystem>() : nullptr;
}

std::string UOdysseyBackendSubsystem::NewUuid()
{
	// FGuid::NewGuid uses the platform's random UUID generator; FormatUuidV4 stamps the RFC 4122
	// version/variant bits and formats it (the backend accepts any [A-Za-z0-9_.:-]{8,128}).
	const FGuid G = FGuid::NewGuid();
	std::array<uint8_t, 16> Bytes{};
	const uint32 Parts[4] = {G.A, G.B, G.C, G.D};
	for (int32 I = 0; I < 4; ++I)
	{
		for (int32 J = 0; J < 4; ++J)
		{
			Bytes[I * 4 + J] = static_cast<uint8_t>((Parts[I] >> (24 - 8 * J)) & 0xFF);
		}
	}
	return odyssey::FormatUuidV4(Bytes);
}

void UOdysseyBackendSubsystem::StartSession()
{
	const UOdysseyBackendSettings* Settings = GetDefault<UOdysseyBackendSettings>();
	if (Settings->IsAndroidJudgeOffline())
	{
		return;
	}
	EnvName = Settings->GetActiveEnvironmentName();
	FString Error;
	if (!Settings->ResolveActiveEnvironment(Env, Error))
	{
		LastError = Error;
		UE_LOG(LogOdysseyBackend, Error, TEXT("%s"), *Error);
		OnBackendError.Broadcast(Error);
		return;
	}
	++SessionGeneration;
	Timers.Reset();
	IntentsInFlight.Reset();
	bReadyBroadcast = false;
	if (Realtime)
	{
		Realtime->Close();
	}
	odyssey::ClientConfig Cfg;
	Cfg.apiPrefix = ToStd(Env.ApiPrefix);
	Cfg.readyPath = ToStd(Env.ReadyPath);
	Cfg.displayName = ToStd(Settings->DisplayName);
	Cfg.requestTimeoutSeconds = Env.RequestTimeoutSeconds;
	Cfg.commandTimeoutSeconds = Env.CommandTimeoutSeconds;
	Machine = std::make_unique<odyssey::SessionMachine>(Cfg, &UOdysseyBackendSubsystem::NewUuid);
	UE_LOG(LogOdysseyBackend, Log, TEXT("ODYSSEY backend '%s' %s%s (protocol %s)"), *EnvName.ToString(), *Env.ServerRoot,
		*Env.ApiPrefix, UTF8_TO_TCHAR(odyssey::kProtocol));
	Execute(Machine->Start(LoadCredentials()));
}

void UOdysseyBackendSubsystem::ForgetStoredSession()
{
	UGameplayStatics::DeleteGameInSlot(SaveSlotName(), 0);
}

void UOdysseyBackendSubsystem::RequestRestore()
{
	if (Machine)
	{
		Execute(Machine->RequestRestore());
	}
}

// ================================================================ commands / analysis
int64 UOdysseyBackendSubsystem::SubmitIntent(const FOdysseySemanticIntent& Intent)
{
	if (!Machine)
	{
		return 0;
	}
	odyssey::Effects Fx;
	const int64 LocalId = static_cast<int64>(Machine->Submit(ToNative(Intent), Fx));
	IntentsInFlight.Add(LocalId, Intent);
	Execute(MoveTemp(Fx));
	return LocalId;
}

void UOdysseyBackendSubsystem::RequestFutureLens(const TArray<FOdysseySemanticIntent>& Candidates, int32 HorizonTicks)
{
	if (!Machine)
	{
		return;
	}
	using odyssey::json::Value;
	Value Arr = Value::Array();
	int32 Index = 0;
	for (const FOdysseySemanticIntent& C : Candidates)
	{
		Value Cand = Value::Object();
		Cand.set("id", Value::String("candidate_" + std::to_string(Index++)));
		Cand.set("action", Value::String(ToStd(C.Action)));
		if (!C.Target.IsNone())
		{
			Cand.set("target", Value::String(ToStd(C.Target)));
		}
		Value Params = Value::Object();
		for (const FOdysseyIntentParam& P : C.Params)
		{
			Params.set(ToStd(P.Name), P.bIsInteger ? Value::Int(P.IntegerValue) : Value::String(ToStd(P.StringValue)));
		}
		Cand.set("params", Params);
		Arr.push(Cand);
	}
	Execute(Machine->RequestFutureLens(Arr, FMath::Clamp(HorizonTicks, 1, 48)));
}

void UOdysseyBackendSubsystem::RequestBlackBox(const FString& TimelineId, bool bCounterfactuals)
{
	if (Machine)
	{
		Execute(Machine->RequestBlackBox(ToStd(TimelineId), bCounterfactuals));
	}
}

// ================================================================ effect execution
bool UOdysseyBackendSubsystem::Tick(float DeltaTime)
{
	if (!Machine)
	{
		return true;
	}
	const double Now = FPlatformTime::Seconds();
#if !UE_BUILD_SHIPPING
	if (Realtime)
	{
		Realtime->DebugTick(Now);
	}
#endif
	TArray<FString> Due;
	for (const TPair<FString, double>& T : Timers)
	{
		if (T.Value <= Now)
		{
			Due.Add(T.Key);
		}
	}
	for (const FString& Tag : Due)
	{
		Timers.Remove(Tag);
		Execute(Machine->OnTimer(ToStd(Tag)));
	}
	return true;
}

void UOdysseyBackendSubsystem::Execute(odyssey::Effects&& Fx)
{
	if (!Machine)
	{
		return;
	}
	for (const odyssey::Notice& N : Fx.notices)
	{
		HandleNotice(N);
	}
	if (Fx.persistCredentials)
	{
		PersistCredentials();
	}
	if (Fx.wsClose && Realtime)
	{
		Realtime->Close();  // machine-initiated: no OnClosed callback
	}
	for (const std::string& Text : Fx.wsSend)
	{
		if (Realtime)
		{
			Realtime->Send(ToFString(Text));
		}
	}
	const double Now = FPlatformTime::Seconds();
	for (const odyssey::TimerEffect& T : Fx.timers)
	{
		Timers.Add(ToFString(T.tag), Now + T.delaySeconds);
	}
	for (const odyssey::HttpEffect& H : Fx.http)
	{
		ExecuteHttp(H, SessionGeneration);
	}
	for (const odyssey::WsConnectEffect& W : Fx.wsConnect)
	{
		ConnectRealtime(ToFString(W.path));
	}
}

void UOdysseyBackendSubsystem::ExecuteHttp(const odyssey::HttpEffect& H, uint32 Generation)
{
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(Env.ServerRoot + ToFString(H.path));
	Req->SetVerb(ToFString(H.method));
	Req->SetHeader(TEXT("Accept"), TEXT("application/json"));
	if (H.authorized)
	{
		Req->SetHeader(TEXT("Authorization"), ToFString(Machine->authorizationHeader()));
	}
	for (const auto& Header : H.headers)
	{
		Req->SetHeader(ToFString(Header.first), ToFString(Header.second));
	}
	if (H.method == "POST")
	{
		Req->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
		TArray<uint8> Body;
		Body.Append(reinterpret_cast<const uint8*>(H.body.data()), static_cast<int32>(H.body.size()));
		Req->SetContent(MoveTemp(Body));  // the exact bytes the machine serialized (same bytes on retry)
	}
	Req->SetTimeout(static_cast<float>(H.timeoutSeconds));
	const std::string Tag = H.tag;
	Req->OnProcessRequestComplete().BindWeakLambda(this,
		[this, Tag, Generation](FHttpRequestPtr, FHttpResponsePtr Response, bool bConnectedSuccessfully) {
			if (Generation != SessionGeneration || !Machine)
			{
				return;  // answer for a previous session
			}
			odyssey::HttpResult R;
			if (!bConnectedSuccessfully || !Response.IsValid())
			{
				R.transportFailed = true;
			}
			else
			{
				R.status = Response->GetResponseCode();
				const TArray<uint8>& Content = Response->GetContent();
				R.body.assign(reinterpret_cast<const char*>(Content.GetData()), static_cast<size_t>(Content.Num()));
				R.replayedHeader = Response->GetHeader(TEXT("Idempotent-Replayed")).Equals(TEXT("true"), ESearchCase::IgnoreCase);
				if (R.status == 429)
				{
					UE_LOG(LogOdysseyBackend, Warning, TEXT("rate limited by the backend (%s)"), *ToFString(Tag));
				}
			}
#if !UE_BUILD_SHIPPING
			if (Tag == "command" && DebugLoseResponses > 0 && !R.transportFailed && R.status == 200)
			{
				--DebugLoseResponses;
				UE_LOG(LogOdysseyBackend, Warning, TEXT("[debug] dropping a command response the server applied"));
				R = odyssey::HttpResult();
				R.transportFailed = true;
			}
#endif
			Execute(Machine->OnHttpResponse(Tag, R));
		});
	Req->ProcessRequest();
}

void UOdysseyBackendSubsystem::ConnectRealtime(const FString& Path)
{
	if (!Realtime)
	{
		Realtime = MakeShared<FOdysseyRealtimeConnection>();
	}
	TWeakObjectPtr<UOdysseyBackendSubsystem> Weak(this);
	const uint32 Generation = SessionGeneration;
	Realtime->OnOpened = [Weak, Generation]() {
		if (Weak.IsValid() && Weak->Machine && Generation == Weak->SessionGeneration)
		{
			Weak->Execute(Weak->Machine->OnWsOpened());
		}
	};
	Realtime->OnText = [Weak, Generation](const FString& Text) {
		if (Weak.IsValid() && Weak->Machine && Generation == Weak->SessionGeneration)
		{
			Weak->Execute(Weak->Machine->OnWsText(ToStd(Text)));
		}
	};
	Realtime->OnClosed = [Weak, Generation](int32 Code) {
		if (Weak.IsValid() && Weak->Machine && Generation == Weak->SessionGeneration)
		{
			Weak->Execute(Weak->Machine->OnWsClosed(Code));
		}
	};
	Realtime->Connect(FOdysseyRealtimeConnection::ToWebSocketUrl(Env.ServerRoot, Path), ToFString(Machine->authorizationHeader()));
}

// ================================================================ notices → delegates / router
void UOdysseyBackendSubsystem::HandleNotice(const odyssey::Notice& N)
{
	using odyssey::NoticeKind;
	switch (N.kind)
	{
	case NoticeKind::StateChanged:
		UE_LOG(LogOdysseyBackend, Log, TEXT("session state → %s"), *ToFString(N.detail));
		OnSessionStateChanged.Broadcast(ToUE(Machine->state()));
		break;
	case NoticeKind::SessionReady:
		bReadyBroadcast = true;
		OnSessionReady.Broadcast();
		break;
	case NoticeKind::SnapshotApplied:
		Router->Route(N);
		ReportUnknownIds();
		break;
	case NoticeKind::EventApplied:
	case NoticeKind::InfoEvent:
		Router->Route(N);
		break;
	case NoticeKind::CommandResolved:
	case NoticeKind::CommandSuperseded:
	case NoticeKind::IntentRejected:
	{
		const bool bStaleRetrying = N.kind == NoticeKind::CommandResolved && N.detail == "stale";
		FOdysseyCommandResolution R;
		R.LocalId = static_cast<int64>(N.localId);
		R.Outcome = N.kind == NoticeKind::CommandSuperseded ? FName(TEXT("superseded"))
					: N.kind == NoticeKind::IntentRejected   ? FName(*(TEXT("rejected_locally:") + ToFString(N.detail)))
															 : ToFName(N.detail);
		if (const FOdysseySemanticIntent* In = IntentsInFlight.Find(R.LocalId))
		{
			R.Action = In->Action;
			R.Target = In->Target;
		}
		const odyssey::json::Value& Err = N.data["error"];
		R.ErrorCode = ToFName(Err["code"].asString());
		R.Reason = ToFName(Err["reason"].asString().empty() ? N.data["reason"].asString() : Err["reason"].asString());
		R.StateVersion = N.data["state_version"].isInt() ? N.data["state_version"].asInt() : Machine->model().stateVersion;
		if (!bStaleRetrying)
		{
			IntentsInFlight.Remove(R.LocalId);
		}
		OnCommandResolved.Broadcast(R);  // "stale" is followed by a final resolution for the same id
		break;
	}
	case NoticeKind::RestoreSummary:
	{
		FOdysseyRestoreSummary S;
		S.TicksAdvanced = N.data["ticks_advanced"].asInt();
		for (const odyssey::json::Value& T : N.data["event_types"].items())
		{
			S.EventTypes.Add(ToFName(T.asString()));
		}
		OnRestored.Broadcast(S);
		break;
	}
	case NoticeKind::SessionReplaced:
		bReadyBroadcast = false;
		OnSessionReplaced.Broadcast(ToFString(N.detail));
		break;
	case NoticeKind::SessionInvalid:
		OnSessionInvalid.Broadcast(ToFString(N.detail));
		break;
	case NoticeKind::ProtocolMismatch:
		LastError = ToFString(N.detail);
		UE_LOG(LogOdysseyBackend, Error, TEXT("backend protocol mismatch: %s (client speaks %s)"), *LastError, UTF8_TO_TCHAR(odyssey::kProtocol));
		OnProtocolMismatch.Broadcast(LastError);
		break;
	case NoticeKind::FutureLensReady:
	{
		const odyssey::FutureLensModel L = odyssey::ParseFutureLens(N.data);
		FOdysseyFutureLensView V;
		V.bOk = L.ok;
		V.PredictionMode = ToFName(L.predictionMode);
		V.BaseTick = L.baseTick;
		V.HorizonHours = static_cast<float>(L.horizonHours);
		for (const odyssey::LensBranch& B : L.branches)
		{
			FOdysseyLensBranchView BV;
			BV.Id = ToFName(B.id);
			BV.Action = ToFName(B.action);
			BV.Target = ToFName(B.target);
			BV.bBaseline = B.isBaseline;
			BV.bValid = B.valid;
			BV.RejectionReason = ToFName(B.rejectionReason);
			BV.ProjectedOutcomeTier = ToFName(B.projectedOutcomeTier);
			BV.ConfidenceLevel = ToFName(B.confidenceLevel);
			BV.RiskPeak = static_cast<float>(B.riskPeak);
			for (const odyssey::LensWorldHint& Hint : B.worldHints)
			{
				BV.WorldHints.Add(FString::Printf(TEXT("%s.%s: %s → %s"), *ToFString(Hint.object), *ToFString(Hint.field),
					*ToFString(Hint.now), *ToFString(Hint.after)));
			}
			BV.Warnings = ToNames(B.warnings);
			V.Branches.Add(BV);
		}
		OnFutureLensReady.Broadcast(V);
		break;
	}
	case NoticeKind::BlackBoxReady:
	{
		const odyssey::BlackBoxModel B = odyssey::ParseBlackBox(N.data);
		FOdysseyBlackBoxView V;
		V.bOk = B.ok;
		V.TimelineId = ToFName(B.timelineId);
		V.MissionId = ToFName(B.missionId);
		V.OutcomeTier = ToFName(B.outcomeTier);
		V.Statement = ToFString(B.statement);
		for (const odyssey::CausalNodeModel& Node : B.nodes)
		{
			V.Nodes.Add(FOdysseyCausalNodeView{ToFName(Node.id), ToFName(Node.type), ToFString(Node.label), ToFName(Node.severity),
				Node.hasTick ? Node.simTick : -1});
		}
		for (const odyssey::CausalEdgeModel& E : B.edges)
		{
			V.Edges.Add(FOdysseyCausalEdgeView{ToFName(E.source), ToFName(E.target), ToFName(E.relation)});
		}
		OnBlackBoxReady.Broadcast(V);
		break;
	}
	case NoticeKind::Error:
		LastError = ToFString(N.detail);
		UE_LOG(LogOdysseyBackend, Warning, TEXT("backend: %s"), *LastError);
		OnBackendError.Broadcast(LastError);
		break;
	case NoticeKind::CommandQueued:
	case NoticeKind::CommandSent:
	case NoticeKind::UnknownSemanticIds:
		break;
	}
}

void UOdysseyBackendSubsystem::ReportUnknownIds()
{
	if (!Registry || !Machine)
	{
		return;
	}
	TArray<FName> Fresh;
	for (const std::string& Id : Registry->Native().UnknownInSnapshot(Machine->model()))
	{
		const FName Name = ToFName(Id);
		if (!ReportedUnknown.Contains(Name))
		{
			ReportedUnknown.Add(Name);
			Fresh.Add(Name);
		}
	}
	if (Fresh.Num() > 0)
	{
		// Forward-compatible content (or another world, e.g. LUNA-01 after the transition): presentation
		// skips ids it has no actor for; nothing crashes and nothing is invented.
		UE_LOG(LogOdysseyBackend, Log, TEXT("%d semantic ids from the backend are not in this build's registry (first: %s)"),
			Fresh.Num(), *Fresh[0].ToString());
		OnUnknownSemanticIds.Broadcast(Fresh);
	}
}

// ================================================================ credentials
FString UOdysseyBackendSubsystem::SaveSlotName() const
{
	return FString::Printf(TEXT("OdysseySession_%s"), *EnvName.ToString());
}

odyssey::Credentials UOdysseyBackendSubsystem::LoadCredentials() const
{
	odyssey::Credentials C;
	if (const UOdysseySessionSaveGame* Save = Cast<UOdysseySessionSaveGame>(UGameplayStatics::LoadGameFromSlot(SaveSlotName(), 0)))
	{
		if (Save->ServerRoot == Env.ServerRoot)
		{
			C.sessionId = ToStd(Save->SessionId);
			C.token = ToStd(Save->Token);
			C.lastSeq = Save->LastSeq;
		}
	}
	return C;
}

void UOdysseyBackendSubsystem::PersistCredentials()
{
	const odyssey::Credentials& C = Machine->credentials();
	if (!C.valid())
	{
		return;
	}
	UOdysseySessionSaveGame* Save = Cast<UOdysseySessionSaveGame>(UGameplayStatics::CreateSaveGameObject(UOdysseySessionSaveGame::StaticClass()));
	Save->SessionId = ToFString(C.sessionId);
	Save->Token = ToFString(C.token);
	Save->LastSeq = C.lastSeq;
	Save->ServerRoot = Env.ServerRoot;
	UGameplayStatics::AsyncSaveGameToSlot(Save, SaveSlotName(), 0);
}

// ================================================================ views
const odyssey::MirrorModel* UOdysseyBackendSubsystem::GetMirrorModel() const
{
	return Machine && Machine->model().loaded ? &Machine->model() : nullptr;
}

EOdysseySessionState UOdysseyBackendSubsystem::GetSessionState() const
{
	return Machine ? ToUE(Machine->state()) : EOdysseySessionState::Idle;
}

bool UOdysseyBackendSubsystem::IsSessionReady() const
{
	return Machine && Machine->state() == odyssey::SessionState::Ready && Machine->model().loaded;
}

FOdysseyMissionContext UOdysseyBackendSubsystem::GetMissionContext() const
{
	FOdysseyMissionContext C;
	if (const odyssey::MirrorModel* M = GetMirrorModel())
	{
		C.MissionId = ToFName(M->missionId);
		C.MissionTitle = ToFString(M->missionTitle);
		C.MissionStatus = ToFName(M->missionStatus);
		C.ActivePhase = ToFName(M->activePhase());
		C.PlayerLocation = ToFName(M->playerLocation);
		C.ClockMode = ToFName(M->clock.mode);
		C.PauseReason = ToFName(M->clock.pauseReason);
		C.SimTick = M->clock.simTick;
	}
	return C;
}

FName UOdysseyBackendSubsystem::GetPlayerSemanticLocation() const
{
	const odyssey::MirrorModel* M = GetMirrorModel();
	return M ? ToFName(M->playerLocation) : NAME_None;
}

FOdysseyObjectView UOdysseyBackendSubsystem::GetObjectView(FName ObjectId) const
{
	const odyssey::MirrorModel* M = GetMirrorModel();
	const odyssey::ObjectInfo* O = M ? M->object(ToStd(ObjectId)) : nullptr;
	return O ? ToView(*O, *M) : FOdysseyObjectView();
}

FOdysseyLocationView UOdysseyBackendSubsystem::GetLocationView(FName LocationId) const
{
	FOdysseyLocationView V;
	const odyssey::MirrorModel* M = GetMirrorModel();
	if (const odyssey::LocationInfo* L = M ? M->location(ToStd(LocationId)) : nullptr)
	{
		V.bFound = true;
		V.Id = LocationId;
		V.DisplayName = ToFString(L->name);
		V.Access = ToFName(L->access);
		V.bVisited = L->visited;
	}
	return V;
}

FOdysseyContainerView UOdysseyBackendSubsystem::GetContainerView(FName ContainerId) const
{
	FOdysseyContainerView V;
	const odyssey::MirrorModel* M = GetMirrorModel();
	if (const odyssey::ContainerInfo* C = M ? M->container(ToStd(ContainerId)) : nullptr)
	{
		V.bFound = true;
		V.Id = ContainerId;
		V.MassKg = static_cast<float>(C->massKg);
		for (const odyssey::ItemStack& S : C->items)
		{
			V.Items.Add(FOdysseyContainerItemView{ToFName(S.item), S.quantity});
		}
	}
	return V;
}

FOdysseyCrewView UOdysseyBackendSubsystem::GetCrewView(FName CrewId) const
{
	FOdysseyCrewView V;
	const odyssey::MirrorModel* M = GetMirrorModel();
	if (const odyssey::CrewInfo* C = M ? M->crewMember(ToStd(CrewId)) : nullptr)
	{
		V.bFound = true;
		V.Id = CrewId;
		V.DisplayName = ToFString(C->name);
		V.Role = ToFString(C->role);
		V.Intent = ToFName(C->intent);
		V.Location = ToFName(C->location);
		V.HealthBand = ToFName(C->healthBand);
		V.InvolvedIncidents = ToNames(C->involvedIncidents);
	}
	return V;
}

TArray<FOdysseyIncidentView> UOdysseyBackendSubsystem::GetIncidents(bool bActiveOnly) const
{
	TArray<FOdysseyIncidentView> Out;
	if (const odyssey::MirrorModel* M = GetMirrorModel())
	{
		for (const odyssey::IncidentInfo& I : M->incidents)
		{
			if (bActiveOnly && I.resolved)
			{
				continue;
			}
			Out.Add(FOdysseyIncidentView{ToFName(I.id), ToFName(I.stage), ToFName(I.messageKey), I.resolved,
				ToNames(I.involvedObjects), ToNames(I.involvedCrew)});
		}
	}
	return Out;
}

TArray<FOdysseyObjectiveView> UOdysseyBackendSubsystem::GetObjectives() const
{
	TArray<FOdysseyObjectiveView> Out;
	if (const odyssey::MirrorModel* M = GetMirrorModel())
	{
		for (const odyssey::ObjectiveInfo& O : M->objectives)
		{
			Out.Add(FOdysseyObjectiveView{ToFName(O.id), ToFName(O.status), ToFName(O.messageKey), O.required});
		}
	}
	return Out;
}

TArray<FOdysseyResourceView> UOdysseyBackendSubsystem::GetResources() const
{
	TArray<FOdysseyResourceView> Out;
	if (const odyssey::MirrorModel* M = GetMirrorModel())
	{
		for (const odyssey::ResourceInfo& R : M->resources)
		{
			Out.Add(FOdysseyResourceView{ToFName(R.id), ToFString(R.label), ToFString(R.unit), static_cast<float>(R.value), ToFName(R.warningState)});
		}
	}
	return Out;
}

FOdysseyAuthorizationView UOdysseyBackendSubsystem::GetAuthorization() const
{
	FOdysseyAuthorizationView V;
	if (const odyssey::MirrorModel* M = GetMirrorModel())
	{
		const odyssey::AuthorizationInfo& A = M->authorization;
		V.bPresent = A.present;
		V.Gate = ToFName(A.gate);
		V.Target = ToFName(A.target);
		V.bAvailable = A.available;
		V.bAuthorized = A.authorized;
		for (const odyssey::RequirementInfo& R : A.requirements)
		{
			V.Requirements.Add(FOdysseyRequirementView{ToFName(R.id), R.met, ToFName(R.reason)});
		}
	}
	return V;
}

TArray<FName> UOdysseyBackendSubsystem::GetCertifications() const
{
	const odyssey::MirrorModel* M = GetMirrorModel();
	return M ? ToNames(M->certifications) : TArray<FName>();
}

FOdysseyConnectionStatus UOdysseyBackendSubsystem::GetConnectionStatus() const
{
	FOdysseyConnectionStatus S;
	S.Environment = EnvName;
	S.ServerRoot = Env.ServerRoot + Env.ApiPrefix;
	S.LastError = LastError;
	if (!Machine)
	{
		return S;
	}
	const odyssey::MirrorModel& M = Machine->model();
	S.State = ToUE(Machine->state());
	S.SessionId = ToFString(Machine->credentials().sessionId);
	S.TimelineId = ToFString(M.timelineId);
	S.StateVersion = M.stateVersion;
	S.LastSeq = Machine->sequencer().cursor();
	S.SemanticLocation = ToFName(M.playerLocation);
	S.LastCommand = ToFString(Machine->lastCommandSummary());
	S.RealtimeState = !Realtime ? TEXT("none")
					  : Realtime->GetState() == EOdysseyRealtimeState::Open ? TEXT("open")
					  : Realtime->GetState() == EOdysseyRealtimeState::Connecting ? TEXT("connecting")
																			   : TEXT("closed");
	S.ReconnectAttempts = Machine->reconnectAttempts();
	S.QueuedIntents = static_cast<int32>(Machine->queuedIntents());
	S.DuplicatesDropped = static_cast<int32>(Machine->sequencer().duplicatesDropped());
	const std::vector<const odyssey::IncidentInfo*> Active = M.activeIncidents();
	S.ActiveIncident = Active.empty() ? NAME_None : ToFName(Active.front()->id);
	S.ClockMode = ToFName(M.clock.mode);
	return S;
}

// ================================================================ development fault controls
#if !UE_BUILD_SHIPPING
void UOdysseyBackendSubsystem::DebugDropRealtime()
{
	if (Realtime)
	{
		Realtime->DebugDrop();  // reaches the machine as a 1006 close → restore → reconnect
	}
}

void UOdysseyBackendSubsystem::DebugSetScrambleRealtime(bool bEnabled)
{
	if (!Realtime)
	{
		Realtime = MakeShared<FOdysseyRealtimeConnection>();
	}
	Realtime->bDebugScramble = bEnabled;
}

void UOdysseyBackendSubsystem::DebugForceStaleNextCommand()
{
	if (Machine)
	{
		Machine->DebugForceStaleNextCommand();
	}
}

void UOdysseyBackendSubsystem::DebugVerifyMirror()
{
	if (!Machine || !Machine->credentials().valid())
	{
		return;
	}
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Req = FHttpModule::Get().CreateRequest();
	Req->SetURL(Env.ServerRoot + Env.ApiPrefix + TEXT("/sessions/") + ToFString(Machine->credentials().sessionId) + TEXT("/snapshot"));
	Req->SetVerb(TEXT("GET"));
	Req->SetHeader(TEXT("Authorization"), ToFString(Machine->authorizationHeader()));
	Req->OnProcessRequestComplete().BindWeakLambda(this, [this](FHttpRequestPtr, FHttpResponsePtr Response, bool bOk) {
		if (!Machine || !bOk || !Response.IsValid() || Response->GetResponseCode() != 200)
		{
			OnMirrorVerified.Broadcast(-1, TEXT("snapshot request failed"));
			return;
		}
		const TArray<uint8>& Content = Response->GetContent();
		odyssey::json::ParseResult P = odyssey::json::parse(std::string(reinterpret_cast<const char*>(Content.GetData()), Content.Num()));
		odyssey::StateMirror Server;
		if (!P.ok || !Server.LoadSnapshot(P.value))
		{
			OnMirrorVerified.Broadcast(-1, TEXT("snapshot invalid"));
			return;
		}
		if (Server.model().lastSeq != Machine->model().lastSeq)
		{
			OnMirrorVerified.Broadcast(-1, FString::Printf(TEXT("server at seq %lld, mirror at %lld: retry"), Server.model().lastSeq, Machine->model().lastSeq));
			return;
		}
		const std::vector<std::string> Diffs = odyssey::DiffMirrors(Machine->model(), Server.model());
		for (const std::string& D : Diffs)
		{
			UE_LOG(LogOdysseyBackend, Warning, TEXT("mirror differs: %s"), *ToFString(D));
		}
		OnMirrorVerified.Broadcast(static_cast<int32>(Diffs.size()), Diffs.empty() ? FString() : ToFString(Diffs.front()));
	});
	Req->ProcessRequest();
}
#endif
