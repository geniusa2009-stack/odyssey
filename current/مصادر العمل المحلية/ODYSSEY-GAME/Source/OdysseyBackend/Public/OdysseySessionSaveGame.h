// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Persisted session credentials (Saved/SaveGames/OdysseySession_<env>.sav). The token is the
// backend's per-session bearer token — never written to Config/ or source control. It is stored
// unencrypted at rest (Phase 6 risk, see Docs/BACKEND_INTEGRATION.md).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"

#include "OdysseySessionSaveGame.generated.h"

UCLASS()
class ODYSSEYBACKEND_API UOdysseySessionSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY() FString SessionId;
	UPROPERTY() FString Token;
	UPROPERTY() int64 LastSeq = 0;
	UPROPERTY() FString ServerRoot;  // credentials are only reused against the same server
};
