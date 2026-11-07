



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
	UPROPERTY() FString ServerRoot;  
};
