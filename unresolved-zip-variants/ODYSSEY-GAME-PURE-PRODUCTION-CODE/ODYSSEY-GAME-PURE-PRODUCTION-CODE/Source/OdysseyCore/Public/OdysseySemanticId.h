



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




USTRUCT(BlueprintType)
struct ODYSSEYCORE_API FOdysseySemanticIdRow : public FTableRowBase
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FName Id;

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString Kind;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString World;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString DisplayName;

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FName Location;

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	FString Binding;

	
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Odyssey|Semantic")
	bool RequiredInSlice = false;
};



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
