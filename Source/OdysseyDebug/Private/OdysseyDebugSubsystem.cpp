// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseyDebugSubsystem.h"

#if !UE_BUILD_SHIPPING
#include "CanvasItem.h"
#include "Debug/DebugDrawService.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "OdysseyBackendSubsystem.h"
#include "OdysseyInteractorComponent.h"
#endif

bool UOdysseyDebugSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
#if UE_BUILD_SHIPPING
	return false;
#else
	return Super::ShouldCreateSubsystem(Outer);
#endif
}

void UOdysseyDebugSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
#if !UE_BUILD_SHIPPING
	UOdysseyBackendSubsystem* B = Collection.InitializeDependency<UOdysseyBackendSubsystem>();
	if (B)
	{
		B->OnMirrorVerified.AddDynamic(this, &UOdysseyDebugSubsystem::HandleVerified);
	}
	DrawHandle = UDebugDrawService::Register(TEXT("Game"), FDebugDrawDelegate::CreateUObject(this, &UOdysseyDebugSubsystem::Draw));
	IConsoleManager& CM = IConsoleManager::Get();
	TWeakObjectPtr<UOdysseyDebugSubsystem> Weak(this);
	auto Backend = [Weak]() -> UOdysseyBackendSubsystem* {
		return Weak.IsValid() ? Weak->GetGameInstance()->GetSubsystem<UOdysseyBackendSubsystem>() : nullptr;
	};
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Debug.Overlay"), TEXT("Toggle the ODYSSEY connection overlay"),
		FConsoleCommandWithArgsDelegate::CreateLambda([Weak](const TArray<FString>& A) {
			if (Weak.IsValid()) Weak->bOverlay = A.Num() > 0 ? FCString::Atoi(*A[0]) != 0 : !Weak->bOverlay;
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.LoseCommandResponse"), TEXT("Drop the next N command responses after the server applied them"),
		FConsoleCommandWithArgsDelegate::CreateLambda([Backend](const TArray<FString>& A) {
			if (UOdysseyBackendSubsystem* S = Backend()) S->DebugLoseNextCommandResponses(A.Num() > 0 ? FCString::Atoi(*A[0]) : 1);
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.DropRealtime"), TEXT("Drop the realtime socket"),
		FConsoleCommandDelegate::CreateLambda([Backend]() {
			if (UOdysseyBackendSubsystem* S = Backend()) S->DebugDropRealtime();
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.Scramble"), TEXT("Deliver realtime events duplicated and out of order (0/1)"),
		FConsoleCommandWithArgsDelegate::CreateLambda([Backend](const TArray<FString>& A) {
			if (UOdysseyBackendSubsystem* S = Backend()) S->DebugSetScrambleRealtime(A.Num() == 0 || FCString::Atoi(*A[0]) != 0);
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.ForceStale"), TEXT("Send the next command with an outdated state version"),
		FConsoleCommandDelegate::CreateLambda([Backend]() {
			if (UOdysseyBackendSubsystem* S = Backend()) S->DebugForceStaleNextCommand();
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.Restore"), TEXT("Restore/resync from the backend now"),
		FConsoleCommandDelegate::CreateLambda([Backend]() {
			if (UOdysseyBackendSubsystem* S = Backend()) S->RequestRestore();
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Net.VerifyMirror"), TEXT("Diff the local mirror against a fresh server snapshot"),
		FConsoleCommandDelegate::CreateLambda([Backend]() {
			if (UOdysseyBackendSubsystem* S = Backend()) S->DebugVerifyMirror();
		})));
	// Odyssey.Act <action> [target|-] [name=value ...]   e.g.  Odyssey.Act mission.clock_set - mode=ACCELERATED
	// Submits a semantic intent exactly as gameplay would (the backend still validates it).
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Act"), TEXT("Submit a semantic intent: <action> [target|-] [name=value ...]"),
		FConsoleCommandWithArgsDelegate::CreateLambda([Backend](const TArray<FString>& A) {
			UOdysseyBackendSubsystem* S = Backend();
			if (!S || A.Num() == 0) return;
			FOdysseySemanticIntent Intent;
			Intent.Action = FName(*A[0]);
			if (A.Num() > 1 && A[1] != TEXT("-")) Intent.Target = FName(*A[1]);
			for (int32 I = 2; I < A.Num(); ++I)
			{
				FString Name, Value;
				if (!A[I].Split(TEXT("="), &Name, &Value)) continue;
				FOdysseyIntentParam P;
				P.Name = FName(*Name);
				P.bIsInteger = Value.IsNumeric() && !Value.Contains(TEXT("."));
				P.IntegerValue = P.bIsInteger ? FCString::Atoi64(*Value) : 0;
				P.StringValue = Value;
				Intent.Params.Add(P);
			}
			Intent.Anchor = TEXT("DevConsole");
			S->SubmitIntent(Intent);
		})));
	Commands.Add(CM.RegisterConsoleCommand(TEXT("Odyssey.Session.Forget"), TEXT("Forget the stored session credentials"),
		FConsoleCommandDelegate::CreateLambda([Backend]() {
			if (UOdysseyBackendSubsystem* S = Backend()) S->ForgetStoredSession();
		})));
#endif
}

void UOdysseyDebugSubsystem::Deinitialize()
{
#if !UE_BUILD_SHIPPING
	UDebugDrawService::Unregister(DrawHandle);
	for (IConsoleObject* C : Commands)
	{
		IConsoleManager::Get().UnregisterConsoleObject(C);
	}
	Commands.Reset();
#endif
	Super::Deinitialize();
}

void UOdysseyDebugSubsystem::HandleVerified(int32 Count, const FString& First)
{
#if !UE_BUILD_SHIPPING
	LastVerify = Count == 0 ? TEXT("mirror == server") : Count < 0 ? First : FString::Printf(TEXT("%d differences (%s)"), Count, *First);
#endif
}

#if !UE_BUILD_SHIPPING
void UOdysseyDebugSubsystem::Draw(UCanvas* Canvas, APlayerController* PC)
{
	const UOdysseyBackendSubsystem* B = GetGameInstance()->GetSubsystem<UOdysseyBackendSubsystem>();
	if (!bOverlay || !Canvas || !B)
	{
		return;
	}
	const FOdysseyConnectionStatus S = B->GetConnectionStatus();
	const UEnum* StateEnum = StaticEnum<EOdysseySessionState>();
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	const UOdysseyInteractorComponent* I = Pawn ? Pawn->FindComponentByClass<UOdysseyInteractorComponent>() : nullptr;
	const FName Target = I ? I->GetFocusedSemanticId() : NAME_None;
	TArray<FString> Lines;
	Lines.Add(FString::Printf(TEXT("ODYSSEY [dev]  %s  %s"), *S.Environment.ToString(), *S.ServerRoot));
	Lines.Add(FString::Printf(TEXT("connection  %s   realtime %s   reconnects %d"),
		*StateEnum->GetNameStringByValue(static_cast<int64>(S.State)), *S.RealtimeState, S.ReconnectAttempts));
	Lines.Add(FString::Printf(TEXT("session     %s"), *S.SessionId));
	Lines.Add(FString::Printf(TEXT("timeline    %s"), *S.TimelineId));
	Lines.Add(FString::Printf(TEXT("state v%lld   last seq %lld   dup dropped %d   queued %d"), S.StateVersion, S.LastSeq, S.DuplicatesDropped, S.QueuedIntents));
	Lines.Add(FString::Printf(TEXT("location    %s   clock %s"), *S.SemanticLocation.ToString(), *S.ClockMode.ToString()));
	Lines.Add(FString::Printf(TEXT("incident    %s"), *S.ActiveIncident.ToString()));
	Lines.Add(FString::Printf(TEXT("target      %s"), *Target.ToString()));
	Lines.Add(FString::Printf(TEXT("last cmd    %s"), *S.LastCommand));
	if (!S.LastError.IsEmpty()) Lines.Add(FString::Printf(TEXT("last error  %s"), *S.LastError));
	if (!LastVerify.IsEmpty()) Lines.Add(FString::Printf(TEXT("verify      %s"), *LastVerify));
	float Y = 40.f;
	for (const FString& L : Lines)
	{
		FCanvasTextItem Item(FVector2D(24.f, Y), FText::FromString(L), GEngine->GetSmallFont(), FLinearColor(0.75f, 0.95f, 1.f));
		Item.EnableShadow(FLinearColor::Black);
		Canvas->DrawItem(Item);
		Y += 14.f;
	}
}
#endif
