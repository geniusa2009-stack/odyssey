



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

	
	bool LoadFromTable(const UDataTable* Table, FString& Error);

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	bool IsKnown(FName Id) const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	bool FindRow(FName Id, FOdysseySemanticIdRow& OutRow) const;

	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	static EOdysseySemanticKind KindOf(const FOdysseySemanticIdRow& Row);

	
	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	TArray<FName> GetRequiredInSlice() const;

	
	UFUNCTION(BlueprintPure, Category = "Odyssey|Semantic")
	TArray<FName> GetAllIds() const;

	const odyssey::SemanticRegistry& Native() const { return Native_; }
	odyssey::SemanticRegistry& NativeMutable() { return Native_; }

	
	static bool TableToNativeRows(const UDataTable* Table, odyssey::json::Value& OutRows);

private:
	TMap<FName, FOdysseySemanticIdRow> Rows;
	odyssey::SemanticRegistry Native_;
};
