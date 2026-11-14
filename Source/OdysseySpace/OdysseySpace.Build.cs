// ODYSSEY space experience: celestial bodies, transit vehicle, travel director, animated logo,
// front-end / navigation HUD and the space game mode. Presentation only - no backend semantics.
using UnrealBuildTool;

public class OdysseySpace : ModuleRules
{
	public OdysseySpace(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "UMG" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
	}
}
