// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// Semantic anchors, zones, bindings, world reaction components, crew placeholders.
using UnrealBuildTool;

public class OdysseyWorld : ModuleRules
{
	public OdysseyWorld(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "OdysseyAPI", "OdysseyCore", "OdysseyBackend", "OdysseyRealtime" });
		PrivateDependencyModuleNames.AddRange(new string[] { "AIModule", "StateTreeModule", "GameplayStateTreeModule", "SmartObjectsModule" });
	}
}
