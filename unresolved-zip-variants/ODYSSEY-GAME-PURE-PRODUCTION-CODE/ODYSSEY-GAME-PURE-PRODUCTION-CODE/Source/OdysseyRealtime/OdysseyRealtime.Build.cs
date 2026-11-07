

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
