"""Rebuild the visual layer after structural/gameplay validation. Does not save the map or claim acceptance."""
from pathlib import Path
import runpy,unreal
here=Path(__file__).resolve().parent
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world and world.get_path_name().startswith("/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice."), "Load the validated slice first."
for name in ["recover_interrupted_capture.py","prepare_console.py","build_production_architecture.py","import_console_unreal.py","import_pack_unreal.py","create_production_materials.py","create_production_glass.py","import_production_modules.py","apply_production_scene.py","apply_production_modules.py","prepare_clean_console.py","import_clean_console.py","finish_clean_console.py","build_service_details.py","import_service_details.py"]:
    unreal.log("[ODYSSEY Production] "+name)
    runpy.run_path(str(here/name),run_name="__main__")
unreal.log("[ODYSSEY Production] Visual layer built, unsaved. Review real-editor captures and rerun gameplay validation before saving/acceptance.")
