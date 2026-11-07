

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
