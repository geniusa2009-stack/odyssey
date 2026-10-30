// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// WebSocket transport (IWebSocket) and the typed event router.
using UnrealBuildTool;

public class OdysseyRealtime : ModuleRules
{
	public OdysseyRealtime(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "OdysseyAPI", "OdysseyCore" });
		PrivateDependencyModuleNames.AddRange(new string[] { "WebSockets" });
	}
}
