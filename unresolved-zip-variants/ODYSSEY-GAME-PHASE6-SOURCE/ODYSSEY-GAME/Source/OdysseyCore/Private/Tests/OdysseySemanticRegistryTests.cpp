// UNREAL_EDITOR_VERIFICATION_REQUIRED: Unreal automation test (Session Frontend → Automation, or
//   UnrealEditor-Cmd Odyssey.uproject -ExecCmds="Automation RunTests Odyssey.Semantic; Quit" -unattended -nullrhi
// Imports the generated registry JSON through Unreal's own DataTable JSON importer into
// FOdysseySemanticIdRow, converts it back for the protocol core, and checks it covers the real
// backend bootstrap fixture. This is the part the native tests cannot cover (UE import path).
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Engine/DataTable.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "OdysseySemanticId.h"
#include "OdysseySemanticRegistry.h"
#include "OdysseyProtocol/StateMirror.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FOdysseySemanticRegistryImportTest, "Odyssey.Semantic.RegistryImport",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)

bool FOdysseySemanticRegistryImportTest::RunTest(const FString& Parameters)
{
	FString Json;
	const FString Path = FPaths::ProjectContentDir() / TEXT("Systems/SemanticIds/DT_SemanticIds_EarthCommand.json");
	if (!TestTrue(TEXT("registry JSON readable"), FFileHelper::LoadFileToString(Json, *Path)))
	{
		return false;
	}
	UDataTable* Table = NewObject<UDataTable>(GetTransientPackage());
	Table->RowStruct = FOdysseySemanticIdRow::StaticStruct();
	const TArray<FString> Problems = Table->CreateTableFromJSONString(Json);
	TestEqual(TEXT("no import problems"), Problems.Num(), 0);
	TestTrue(TEXT("rows imported"), Table->GetRowMap().Num() >= 30);

	const FOdysseySemanticIdRow* Bus = Table->FindRow<FOdysseySemanticIdRow>(TEXT("earth.command.engineering.power_bus_b"), TEXT("test"));
	TestNotNull(TEXT("power bus B row"), Bus);
	if (Bus)
	{
		TestEqual(TEXT("kind"), UOdysseySemanticRegistry::KindOf(*Bus), EOdysseySemanticKind::Object);
		TestEqual(TEXT("location"), Bus->Location, FName(TEXT("earth.command.engineering")));
		TestTrue(TEXT("required in slice"), Bus->RequiredInSlice);
	}

	odyssey::json::Value Rows;
	TestTrue(TEXT("convert to native rows"), UOdysseySemanticRegistry::TableToNativeRows(Table, Rows));
	odyssey::SemanticRegistry Native;
	std::string Error;
	TestTrue(TEXT("native registry loads the imported rows"), Native.Load(Rows, &Error));

	FString Bootstrap;
	TestTrue(TEXT("bootstrap fixture readable"),
		FFileHelper::LoadFileToString(Bootstrap, *(FPaths::ProjectDir() / TEXT("Tests/Fixtures/odyssey.game.v1/examples/bootstrap.json"))));
	const FTCHARToUTF8 Utf8(*Bootstrap);
	odyssey::json::ParseResult Parsed = odyssey::json::parse(std::string(Utf8.Get(), Utf8.Length()));
	TestTrue(TEXT("bootstrap parses"), Parsed.ok);
	odyssey::StateMirror Mirror;
	TestTrue(TEXT("snapshot loads"), Mirror.LoadSnapshot(Parsed.value["snapshot"]));
	TestEqual(TEXT("every bootstrap id is registered"), static_cast<int32>(Native.UnknownInSnapshot(Mirror.model()).size()), 0);
	return true;
}

#endif
