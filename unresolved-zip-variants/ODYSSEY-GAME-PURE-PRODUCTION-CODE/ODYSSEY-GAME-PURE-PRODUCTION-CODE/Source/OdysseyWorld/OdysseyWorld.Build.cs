

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
