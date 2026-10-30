// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet run inside Unreal Engine 5.8.
// Runs every shared protocol test case (ProtocolTestCases.h — the same bodies the native runner
// executes, 26 cases / 959 checks passing natively) as Unreal automation tests "Odyssey.Protocol.*":
//   UnrealEditor-Cmd <path>/Odyssey.uproject -ExecCmds="Automation RunTests Odyssey; Quit" \
//     -unattended -nullrhi -nosplash -log -ReportExportPath=<dir>
// Fixtures are read from <project>/Tests/Fixtures/odyssey.game.v1 (vendored backend output).
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Tests/ProtocolTestCases.h"

namespace
{
class FUnrealProtocolContext final : public odyssey::tests::Context
{
public:
	explicit FUnrealProtocolContext(FAutomationTestBase& InTest) : Test(InTest) {}

	void Check(bool bOk, const char* Expr, const char* File, int Line) override
	{
		if (!bOk)
		{
			Test.AddError(FString::Printf(TEXT("%s:%d  %s"), *FPaths::GetCleanFilename(UTF8_TO_TCHAR(File)), Line, UTF8_TO_TCHAR(Expr)));
		}
	}

	bool ReadFile(const std::string& RelativePath, std::string& Out) override
	{
		TArray<uint8> Bytes;
		const FString Path = FPaths::ProjectDir() / UTF8_TO_TCHAR(RelativePath.c_str());
		if (!FFileHelper::LoadFileToArray(Bytes, *Path))
		{
			Test.AddError(FString::Printf(TEXT("cannot read %s"), *Path));
			return false;
		}
		Out.assign(reinterpret_cast<const char*>(Bytes.GetData()), static_cast<size_t>(Bytes.Num()));
		return true;
	}

private:
	FAutomationTestBase& Test;
};
}  // namespace

IMPLEMENT_COMPLEX_AUTOMATION_TEST(FOdysseyProtocolTests, "Odyssey.Protocol",
	EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::EngineFilter)

void FOdysseyProtocolTests::GetTests(TArray<FString>& OutBeautifiedNames, TArray<FString>& OutTestCommands) const
{
	for (const odyssey::tests::Case& C : odyssey::tests::AllCases())
	{
		OutBeautifiedNames.Add(UTF8_TO_TCHAR(C.name));
		OutTestCommands.Add(UTF8_TO_TCHAR(C.name));
	}
}

bool FOdysseyProtocolTests::RunTest(const FString& Parameters)
{
	for (const odyssey::tests::Case& C : odyssey::tests::AllCases())
	{
		if (Parameters == UTF8_TO_TCHAR(C.name))
		{
			FUnrealProtocolContext Ctx(*this);
			C.fn(Ctx);
			return !HasAnyErrors();
		}
	}
	AddError(FString::Printf(TEXT("unknown case %s"), *Parameters));
	return false;
}

#endif
