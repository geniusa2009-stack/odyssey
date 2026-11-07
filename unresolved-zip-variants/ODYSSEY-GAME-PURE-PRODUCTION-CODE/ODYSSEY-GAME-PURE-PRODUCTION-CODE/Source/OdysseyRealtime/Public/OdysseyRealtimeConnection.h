



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
	TFunction<void(const FString& )> OnText;
	TFunction<void(int32 )> OnClosed;  

	~FOdysseyRealtimeConnection();

	
	void Connect(const FString& Url, const FString& Authorization);
	void Close();
	bool Send(const FString& Text);
	EOdysseyRealtimeState GetState() const { return State; }

#if !UE_BUILD_SHIPPING
	
	bool bDebugScramble = false;
	
	void DebugDrop();
	
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
