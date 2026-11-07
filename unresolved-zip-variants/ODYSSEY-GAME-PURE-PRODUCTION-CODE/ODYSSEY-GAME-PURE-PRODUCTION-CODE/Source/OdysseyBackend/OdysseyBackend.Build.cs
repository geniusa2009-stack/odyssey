

using UnrealBuildTool;

public class OdysseyBackend : ModuleRules
{
	public OdysseyBackend(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "OdysseyAPI", "OdysseyCore", "OdysseyRealtime" });
		PrivateDependencyModuleNames.AddRange(new string[] { "HTTP", "WebSockets" });
	}
}
