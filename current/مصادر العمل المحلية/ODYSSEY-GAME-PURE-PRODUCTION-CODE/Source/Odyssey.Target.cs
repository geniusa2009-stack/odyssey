
using UnrealBuildTool;

public class OdysseyTarget : TargetRules
{
	public OdysseyTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.AddRange(new string[] {
			"OdysseyCore", "OdysseyBackend", "OdysseyRealtime", "OdysseyWorld",
			"OdysseyInteraction", "OdysseyPlayer", "OdysseyUI", "OdysseyDebug" });
	}
}
