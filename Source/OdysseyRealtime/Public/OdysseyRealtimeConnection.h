// UNREAL_EDITOR_VERIFICATION_REQUIRED
// The dedicated realtime transport: one IWebSocket per session. It knows nothing about the
// protocol: frames go to the session machine (odyssey::SessionMachine::OnWsText), which owns
// ordering, duplicates, resume cursors and resync. Only the machine decides to (re)connect.
#pragma once

#include "CoreMinimal.h"
#include "Templates/Function.h"

class IWebSocket;

enum class EOdysseyRealtimeState : uint8
{
	Closed,
	Connecting,
	Open,
};

class ODYSSEYREALTIME_API FOdysseyRealtimeConnection : public TSharedFromThis<FOdysseyRealtimeConnection>
{
public:
	TFunction<void()> OnOpened;
	TFunction<void(const FString& /*Text*/)> OnText;
	TFunction<void(int32 /*Code*/)> OnClosed;  // not called for a Close() we initiated

	~FOdysseyRealtimeConnection();

	// Url: ws:// or wss:// + path (the token travels in the Authorization header, not the URL).
	void Connect(const FString& Url, const FString& Authorization);
	void Close();
	bool Send(const FString& Text);
	EOdysseyRealtimeState GetState() const { return State; }

#if !UE_BUILD_SHIPPING
	// Development fault injection (Docs/TESTING.md): deliver event frames out of order and twice.
	bool bDebugScramble = false;
	// Drop the socket abruptly as if the network failed (the machine sees a 1006 close).
	void DebugDrop();
	// Called every tick: releases a frame held by scrambling after 0.3 s without a successor.
	void DebugTick(double NowSeconds);
#endif

	static FString ToWebSocketUrl(const FString& HttpServerRoot, const FString& Path);

private:
	void Deliver(const FString& Text);
	void Unbind();

	TSharedPtr<IWebSocket> Socket;
	EOdysseyRealtimeState State = EOdysseyRealtimeState::Closed;
#if !UE_BUILD_SHIPPING
	FString Held;
	double HeldAt = 0.0;
#endif
};
