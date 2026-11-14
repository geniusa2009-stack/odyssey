// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// Minimal HUD, ORION presentation interface, Future Lens / Black Box debug views.
using UnrealBuildTool;

public class OdysseyUI : ModuleRules
{
	public OdysseyUI(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "UMG", "OdysseyAPI", "OdysseyCore", "OdysseyBackend", "OdysseyRealtime", "OdysseyInteraction" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore", "InputCore" });
	}
}
