

using UnrealBuildTool;

public class OdysseyDebug : ModuleRules
{
	public OdysseyDebug(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "OdysseyAPI", "OdysseyCore", "OdysseyBackend", "OdysseyRealtime", "OdysseyInteraction" });
		PrivateDependencyModuleNames.AddRange(new string[] {  });
	}
}
