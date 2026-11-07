// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// Development-only overlay and network fault controls (compiled out of Shipping).
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
