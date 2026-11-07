
#include "OdysseyRealtimeConnection.h"

#include "IWebSocket.h"
#include "OdysseyCore.h"
#include "HAL/PlatformTime.h"
#include "WebSocketsModule.h"

FOdysseyRealtimeConnection::~FOdysseyRealtimeConnection()
{
	Unbind();
	if (Socket.IsValid() && Socket->IsConnected())
	{
		Socket->Close();
	}
}

FString FOdysseyRealtimeConnection::ToWebSocketUrl(const FString& HttpServerRoot, const FString& Path)
{
	FString Root = HttpServerRoot;
	if (Root.StartsWith(TEXT("https://")))
	{
		Root = TEXT("wss://") + Root.RightChop(8);
	}
	else if (Root.StartsWith(TEXT("http://")))
	{
		Root = TEXT("ws://") + Root.RightChop(7);
	}
	return Root + Path;
}

void FOdysseyRealtimeConnection::Connect(const FString& Url, const FString& Authorization)
{
	Close();
	TMap<FString, FString> Headers;
	Headers.Add(TEXT("Authorization"), Authorization);
	
	Socket = FWebSocketsModule::Get().CreateWebSocket(Url, TEXT(""), Headers);
	State = EOdysseyRealtimeState::Connecting;
	TWeakPtr<FOdysseyRealtimeConnection> Weak = AsShared();

	Socket->OnConnected().AddLambda([Weak]() {
		if (TSharedPtr<FOdysseyRealtimeConnection> Self = Weak.Pin())
		{
			Self->State = EOdysseyRealtimeState::Open;
			if (Self->OnOpened) Self->OnOpened();
		}
	});
	Socket->OnConnectionError().AddLambda([Weak](const FString& Error) {
		if (TSharedPtr<FOdysseyRealtimeConnection> Self = Weak.Pin())
		{
			UE_LOG(LogOdysseyRealtime, Warning, TEXT("realtime connection error: %s"), *Error);
			Self->State = EOdysseyRealtimeState::Closed;
			if (Self->OnClosed) Self->OnClosed(1006);
		}
	});
	Socket->OnClosed().AddLambda([Weak](int32 StatusCode, const FString& Reason, bool bWasClean) {
		if (TSharedPtr<FOdysseyRealtimeConnection> Self = Weak.Pin())
		{
			UE_LOG(LogOdysseyRealtime, Log, TEXT("realtime closed %d (%s) clean=%d"), StatusCode, *Reason, bWasClean ? 1 : 0);
			Self->State = EOdysseyRealtimeState::Closed;
			if (Self->OnClosed) Self->OnClosed(bWasClean ? StatusCode : 1006);
		}
	});
	Socket->OnMessage().AddLambda([Weak](const FString& Text) {
		if (TSharedPtr<FOdysseyRealtimeConnection> Self = Weak.Pin())
		{
			Self->Deliver(Text);
		}
	});
	Socket->Connect();
}

void FOdysseyRealtimeConnection::Unbind()
{
	if (Socket.IsValid())
	{
		Socket->OnConnected().Clear();
		Socket->OnConnectionError().Clear();
		Socket->OnClosed().Clear();
		Socket->OnMessage().Clear();
	}
}

void FOdysseyRealtimeConnection::Close()
{
	if (!Socket.IsValid())
	{
		return;
	}
	Unbind();  
	if (Socket->IsConnected())
	{
		Socket->Close(1000, TEXT("client"));
	}
	Socket.Reset();
	State = EOdysseyRealtimeState::Closed;
#if !UE_BUILD_SHIPPING
	Held.Reset();
#endif
}

bool FOdysseyRealtimeConnection::Send(const FString& Text)
{
	if (!Socket.IsValid() || !Socket->IsConnected())
	{
		return false;
	}
	Socket->Send(Text);
	return true;
}

void FOdysseyRealtimeConnection::Deliver(const FString& Text)
{
	if (!OnText)
	{
		return;
	}
#if !UE_BUILD_SHIPPING
	const bool bEvent = Text.Contains(TEXT("\"event_id\"")) && Text.Contains(TEXT("\"seq\""));
	if (bDebugScramble && bEvent)
	{
		if (Held.IsEmpty())
		{
			Held = Text;
			HeldAt = FPlatformTime::Seconds();
			return;
		}
		const FString First = Held;
		Held.Reset();
		OnText(Text);   
		OnText(First);  
		OnText(First);  
		OnText(Text);   
		return;
	}
	if (!Held.IsEmpty())
	{
		const FString First = Held;
		Held.Reset();
		OnText(First);
	}
#endif
	OnText(Text);
}

#if !UE_BUILD_SHIPPING
void FOdysseyRealtimeConnection::DebugTick(double NowSeconds)
{
	if (!Held.IsEmpty() && NowSeconds - HeldAt > 0.3 && OnText)
	{
		const FString First = Held;
		Held.Reset();
		OnText(First);
	}
}

void FOdysseyRealtimeConnection::DebugDrop()
{
	if (!Socket.IsValid())
	{
		return;
	}
	TFunction<void(int32)> Closed = OnClosed;
	Unbind();
	Socket->Close(4000, TEXT("debug drop"));
	Socket.Reset();
	State = EOdysseyRealtimeState::Closed;
	Held.Reset();
	if (Closed) Closed(1006);
}
#endif
