// UNREAL_EDITOR_VERIFICATION_REQUIRED
// Typed semantic ids. Backend ids (e.g. earth.command.engineering.power_bus_b) are FNames chosen
// from the registry DataTable (DT_SemanticIds_EarthCommand, generated from the backend content);
// actors never carry free-form strings for them.
#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"

#include "OdysseySemanticId.generated.h"

UENUM(BlueprintType)
enum class EOdysseySemanticKind : uint8
{
	Unknown,
	Location,
	Object,
	Container,
	Crew,
};

// Row struct of the registry DataTable. Column names match the generated JSON
// (Tools/SemanticIds/generate_registry.py); Kind stays a string so the import never depends on
// enum spelling — use UOdysseySemanticRegistry::KindOf().
USTRUCT(BlueprintType)
struct ODYSSEYCORE_API FOdysseySemanticIdRow : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FName Id;

	// "location" | "object" | "container" | "crew"
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString Kind;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString World;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString DisplayName;

	// Containing location for objects/containers.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FName Location;

	// Recommended actor/anchor name in the greybox (informational only).
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString Binding;

	// Must be represented by an actor in the Earth Command slice map.
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	bool RequiredInSlice = false;
};

// A reference to one backend semantic id. Edited through a dropdown of registry row names
// (meta=(GetOptions)) on the components that use it.
USTRUCT(BlueprintType)
struct ODYSSEYCORE_API FOdysseySemanticId
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Odyssey|Semantic")
	FName Id;

	FOdysseySemanticId() = default;
	explicit FOdysseySemanticId(FName InId) : Id(InId) {}

	bool IsValid() const { return !Id.IsNone(); }
	bool operator==(const FOdysseySemanticId& O) const { return Id == O.Id; }
	friend uint32 GetTypeHash(const FOdysseySemanticId& S) { return GetTypeHash(S.Id); }
	FString ToString() const { return Id.ToString(); }
};
