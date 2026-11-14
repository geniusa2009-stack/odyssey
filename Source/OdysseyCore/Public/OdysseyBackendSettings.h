// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Backend endpoints per environment (Project Settings → Game → ODYSSEY Backend; stored in
// Config/DefaultGame.ini). No secrets: session tokens are issued by the backend at runtime and
// stored in Saved/ (never in source control).
// Environment selection: -OdysseyEnv=<name> on the command line, else the ODYSSEY_ENV environment
// variable, else DefaultEnvironment.
#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"

#include "OdysseyBackendSettings.generated.h"

class UDataTable;

USTRUCT(BlueprintType)
struct ODYSSEYCORE_API FOdysseyBackendEnvironment
{
	GENERATED_BODY()

	// Server root, without the API prefix, e.g. http://127.0.0.1:8000
	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ServerRoot = TEXT("http://127.0.0.1:8000");

	// odyssey.game.v1 prefix (the full development API is http://127.0.0.1:8000/api/game/v1)
	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ApiPrefix = TEXT("/api/game/v1");

	UPROPERTY(EditAnywhere, Config, Category = "Odyssey")
	FString ReadyPath = TEXT("/api/v1/ready");

	// Plain http/ws is refused for this environment unless allowed (development only).
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

	// Registry DataTable (row struct FOdysseySemanticIdRow) imported from
	// Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json.
	UPROPERTY(EditAnywhere, Config, Category = "Semantic Ids", meta = (RequiredAssetDataTags = "RowStructure=/Script/OdysseyCore.OdysseySemanticIdRow"))
	TSoftObjectPtr<UDataTable> SemanticIdTable;

	UPROPERTY(EditAnywhere, Config, Category = "Session")
	FString DisplayName = TEXT("Commander");

	// Start the backend session automatically when the game instance starts.
	UPROPERTY(EditAnywhere, Config, Category = "Session")
	bool bAutoStartSession = true;

	// Judge exploration is opt-in in AndroidGame.ini; desktop always uses the canonical backend.
	UPROPERTY(EditAnywhere, Config, Category = "Session")
	bool bAndroidJudgeOffline = false;

	bool IsAndroidJudgeOffline() const
	{
#if PLATFORM_ANDROID
		return bAndroidJudgeOffline;
#else
		return false;
#endif
	}

	virtual FName GetCategoryName() const override { return TEXT("Game"); }

	FName GetActiveEnvironmentName() const;
	// False (with Error set) when the environment is missing or violates the transport policy.
	bool ResolveActiveEnvironment(FOdysseyBackendEnvironment& Out, FString& Error) const;
};
