// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// Settings (per-environment backend config), semantic id types and registry, string conversion, logging.
using UnrealBuildTool;

public class OdysseyCore : ModuleRules
{
	public OdysseyCore(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings", "OdysseyAPI" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Json", "JsonUtilities" });
	}
}
