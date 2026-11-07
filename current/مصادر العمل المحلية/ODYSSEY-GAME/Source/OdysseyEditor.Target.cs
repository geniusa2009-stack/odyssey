// UNREAL_EDITOR_VERIFICATION_REQUIRED: not yet compiled with UnrealBuildTool 5.8.
using UnrealBuildTool;

public class OdysseyEditorTarget : TargetRules
{
	public OdysseyEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.AddRange(new string[] {
			"OdysseyCore", "OdysseyBackend", "OdysseyRealtime", "OdysseyWorld",
			"OdysseyInteraction", "OdysseyPlayer", "OdysseyUI", "OdysseyDebug" });
	}
}
