// UNREAL_EDITOR_VERIFICATION_REQUIRED
// The data-driven registry of backend semantic ids, loaded once per game instance from the
// registry DataTable and mirrored into the engine-independent odyssey::SemanticRegistry (the same
// class the native tests validate against the backend fixtures).
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "OdysseySemanticId.h"

#include "OdysseyProtocol/SemanticRegistry.h"

#include "OdysseySemanticRegistry.generated.h"

class UDataTable;

UCLASS()
class ODYSSEYCORE_API UOdysseySemanticRegistry : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	// Loads (or reloads) from a table; used by Initialize and by tests.
	bool LoadFromTable(const UDataTable* Table, FString& Error);

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	bool IsKnown(FName Id) const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	bool FindRow(FName Id, FOdysseySemanticIdRow& OutRow) const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	static EOdysseySemanticKind KindOf(const FOdysseySemanticIdRow& Row);

	// Ids required by the slice map; the world subsystem reports those without an actor.
	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	TArray<FName> GetRequiredInSlice() const;

	// All row names (editor dropdowns use this through GetOptions).
	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	TArray<FName> GetAllIds() const;

	const odyssey::SemanticRegistry& Native() const { return Native_; }
	odyssey::SemanticRegistry& NativeMutable() { return Native_; }

	// Builds the protocol core's row array from a table (exposed for automation tests).
	static bool TableToNativeRows(const UDataTable* Table, odyssey::json::Value& OutRows);

private:
	TMap<FName, FOdysseySemanticIdRow> Rows;
	odyssey::SemanticRegistry Native_;
};
