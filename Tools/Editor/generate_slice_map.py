"""Unreal Editor Python: regenerate the verification map end to end (registry DataTable, Engineering
proxy/kit assets, L_EarthCommand_Slice), rebuilding the greybox folder of an existing map.

Headless (exits when done):
    UnrealEditor-Cmd Odyssey.uproject -run=pythonscript -script="<project>/Tools/Editor/generate_slice_map.py" -unattended -nullrhi
In the editor:
    py "<project>/Tools/Editor/generate_slice_map.py"

Targets are exactly those of import_semantic_registry.py and build_earth_command_greybox.py.
"""
import os
import runpy

import unreal

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(
    unreal.Paths.project_dir(), "Tools", "Editor")

runpy.run_path(os.path.join(HERE, "import_semantic_registry.py"), run_name="__main__")

builder = os.path.join(HERE, "build_earth_command_greybox.py")
with open(builder, encoding="utf-8") as f:
    source = f.read().replace("REBUILD = False", "REBUILD = True", 1)
exec(compile(source, builder, "exec"), {"__name__": "__main__", "__file__": builder})
unreal.log("[Odyssey] generate_slice_map: done")
