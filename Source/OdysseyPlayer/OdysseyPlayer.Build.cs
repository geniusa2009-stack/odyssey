// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// Third-person character, camera, controller, game mode (spawn at the backend's semantic location).
using UnrealBuildTool;

public class OdysseyPlayer : ModuleRules
{
	public OdysseyPlayer(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "OdysseyCore", "OdysseyBackend", "OdysseyWorld", "OdysseyInteraction", "OdysseyUI" });
		PrivateDependencyModuleNames.AddRange(new string[] {  });
	}
}
