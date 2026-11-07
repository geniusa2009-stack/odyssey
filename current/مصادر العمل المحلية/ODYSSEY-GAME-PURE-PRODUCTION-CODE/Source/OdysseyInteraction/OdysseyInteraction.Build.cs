

using UnrealBuildTool;

public class OdysseyInteraction : ModuleRules
{
	public OdysseyInteraction(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "OdysseyAPI", "OdysseyCore", "OdysseyBackend", "OdysseyRealtime", "OdysseyWorld", "UMG" });
		PrivateDependencyModuleNames.AddRange(new string[] {  });
	}
}
