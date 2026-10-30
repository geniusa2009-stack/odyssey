// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// UOdysseyInteractableComponent, the player's interactor, the Engineering power console.
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
