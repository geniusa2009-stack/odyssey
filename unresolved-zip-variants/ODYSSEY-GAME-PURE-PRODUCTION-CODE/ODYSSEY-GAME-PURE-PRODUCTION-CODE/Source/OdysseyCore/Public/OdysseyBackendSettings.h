





#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"

#include "OdysseyBackendSettings.generated.h"

class UDataTable;

USTRUCT(BlueprintType)
struct ODYSSEYCORE_API FOdysseyBackendEnvironment
{
	GENERATED_BODY()

	
	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ServerRoot = TEXT("http://127.0.0.1:8000");

	
	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ApiPrefix = TEXT("/api/game/v1");

	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ReadyPath = TEXT("/api/v1/ready");

	
	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	bool bAllowInsecureTransport = false;

	UPROPERTY(EditAnywhere, Config, Category = "Odyssey", meta = (ClampMin = "1.0"))
	float RequestTimeoutSeconds = 10.f;

	UPROPERTY(EditAnywhere, Config, Category = "Odyssey", meta = (ClampMin = "1.0"))
	float CommandTimeoutSeconds = 10.f;
};

UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "ODYSSEY Backend"))
class ODYSSEYCORE_API UOdysseyBackendSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, Config, Category = "Environments")
	FName DefaultEnvironment = TEXT("development");

	UPROPERTY(EditAnywhere, Config, Category = "Environments")
	TMap<FName, FOdysseyBackendEnvironment> Environments;

	
	
	UPROPERTY(EditAnywhere, Config, Category = "Semantic Ids", meta = (RequiredAssetDataTags = "RowStructure=/Script/OdysseyCore.OdysseySemanticIdRow"))
	TSoftObjectPtr<UDataTable> SemanticIdTable;

	UPROPERTY(EditAnywhere, Config, Category = "Session")
	FString DisplayName = TEXT("Commander");

	
	UPROPERTY(EditAnywhere, Config, Category = "Session")
	bool bAutoStartSession = true;

	virtual FName GetCategoryName() const override { return TEXT("Game"); }

	FName GetActiveEnvironmentName() const;
	
	bool ResolveActiveEnvironment(FOdysseyBackendEnvironment& Out, FString& Error) const;
};
