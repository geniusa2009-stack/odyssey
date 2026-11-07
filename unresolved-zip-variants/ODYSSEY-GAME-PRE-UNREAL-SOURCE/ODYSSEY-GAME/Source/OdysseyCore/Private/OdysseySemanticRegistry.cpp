// UNREAL_EDITOR_VERIFICATION_REQUIRED
#include "OdysseySemanticRegistry.h"

#include "Engine/DataTable.h"
#include "OdysseyBackendSettings.h"
#include "OdysseyCore.h"
#include "OdysseyStringConv.h"

using namespace OdysseyConv;

void UOdysseySemanticRegistry::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	const UOdysseyBackendSettings* Settings = GetDefault<UOdysseyBackendSettings>();
	const UDataTable* Table = Settings->SemanticIdTable.LoadSynchronous();
	FString Error;
	if (!Table)
	{
		UE_LOG(LogOdyssey, Error, TEXT("Semantic id registry: no DataTable configured (Project Settings → ODYSSEY Backend → SemanticIdTable)"));
		return;
	}
	if (!LoadFromTable(Table, Error))
	{
		UE_LOG(LogOdyssey, Error, TEXT("Semantic id registry: %s"), *Error);
		return;
	}
	UE_LOG(LogOdyssey, Log, TEXT("Semantic id registry: %d ids from %s"), Rows.Num(), *Table->GetPathName());
}

bool UOdysseySemanticRegistry::TableToNativeRows(const UDataTable* Table, odyssey::json::Value& OutRows)
{
	using odyssey::json::Value;
	if (!Table || Table->GetRowStruct() != FOdysseySemanticIdRow::StaticStruct())
	{
		return false;
	}
	OutRows = Value::Array();
	for (const TPair<FName, uint8*>& It : Table->GetRowMap())
	{
		const FOdysseySemanticIdRow* Row = reinterpret_cast<const FOdysseySemanticIdRow*>(It.Value);
		Value R = Value::Object();
		R.set("Name", Value::String(ToStd(It.Key)));
		R.set("Id", Value::String(ToStd(Row->Id)));
		R.set("Kind", Value::String(ToStd(Row->Kind)));
		R.set("World", Value::String(ToStd(Row->World)));
		R.set("DisplayName", Value::String(ToStd(Row->DisplayName)));
		R.set("Location", Value::String(ToStd(Row->Location)));
		R.set("Binding", Value::String(ToStd(Row->Binding)));
		R.set("RequiredInSlice", Value::Bool(Row->RequiredInSlice));
		OutRows.push(R);
	}
	return true;
}

bool UOdysseySemanticRegistry::LoadFromTable(const UDataTable* Table, FString& Error)
{
	odyssey::json::Value NativeRows;
	if (!TableToNativeRows(Table, NativeRows))
	{
		Error = TEXT("table missing or its row struct is not FOdysseySemanticIdRow");
		return false;
	}
	std::string NativeError;
	if (!Native_.Load(NativeRows, &NativeError))
	{
		Error = ToFString(NativeError);
		return false;
	}
	Rows.Reset();
	for (const TPair<FName, uint8*>& It : Table->GetRowMap())
	{
		Rows.Add(It.Key, *reinterpret_cast<const FOdysseySemanticIdRow*>(It.Value));
	}
	return true;
}

bool UOdysseySemanticRegistry::IsKnown(FName Id) const
{
	return Rows.Contains(Id);
}

bool UOdysseySemanticRegistry::FindRow(FName Id, FOdysseySemanticIdRow& OutRow) const
{
	if (const FOdysseySemanticIdRow* Row = Rows.Find(Id))
	{
		OutRow = *Row;
		return true;
	}
	return false;
}

EOdysseySemanticKind UOdysseySemanticRegistry::KindOf(const FOdysseySemanticIdRow& Row)
{
	switch (odyssey::ParseSemanticKind(ToStd(Row.Kind)))
	{
	case odyssey::SemanticKind::Location: return EOdysseySemanticKind::Location;
	case odyssey::SemanticKind::Object: return EOdysseySemanticKind::Object;
	case odyssey::SemanticKind::Container: return EOdysseySemanticKind::Container;
	case odyssey::SemanticKind::Crew: return EOdysseySemanticKind::Crew;
	default: return EOdysseySemanticKind::Unknown;
	}
}

TArray<FName> UOdysseySemanticRegistry::GetRequiredInSlice() const
{
	TArray<FName> Out;
	for (const TPair<FName, FOdysseySemanticIdRow>& It : Rows)
	{
		if (It.Value.RequiredInSlice)
		{
			Out.Add(It.Key);
		}
	}
	return Out;
}

TArray<FName> UOdysseySemanticRegistry::GetAllIds() const
{
	TArray<FName> Out;
	Rows.GetKeys(Out);
	Out.Sort(FNameLexicalLess());
	return Out;
}
