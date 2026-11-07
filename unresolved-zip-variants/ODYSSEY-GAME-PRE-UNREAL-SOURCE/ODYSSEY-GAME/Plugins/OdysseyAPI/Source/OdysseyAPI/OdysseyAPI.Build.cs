// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
// The protocol core under Public/OdysseyProtocol is engine-independent standard C++20 (no
// exceptions, no RTTI) and is compiled and tested natively by Tools/ProtocolCore.
using UnrealBuildTool;

public class OdysseyAPI : ModuleRules
{
	public OdysseyAPI(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		CppStandard = CppStandardVersion.Cpp20;
		bUseUnity = false; // header-only core: keep translation units explicit
		PublicDependencyModuleNames.AddRange(new string[] { "Core" });
		PrivateDependencyModuleNames.AddRange(new string[] { "CoreUObject", "Projects" });
		// Private/Tests/*.h are shared with the native runner; the automation wrapper includes them.
		PrivateIncludePaths.Add(System.IO.Path.Combine(ModuleDirectory, "Private"));
	}
}
