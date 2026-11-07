"""Unreal Editor Python: import the generated semantic id registry as a DataTable asset.

UNREAL_EDITOR_VERIFICATION_REQUIRED — written for UE 5.8 editor scripting; not yet run.

Target (and the ONLY asset this script creates or overwrites):
    /Game/Systems/SemanticIds/DT_SemanticIds_EarthCommand   (row struct FOdysseySemanticIdRow)
Source:
    <project>/Content/Systems/SemanticIds/DT_SemanticIds_EarthCommand.json
    (generated from the backend content by Tools/SemanticIds/generate_registry.py)

Run inside the editor:  py "<project>/Tools/Editor/import_semantic_registry.py"
"""

import os

import unreal

ASSET_DIR = "/Game/Systems/SemanticIds"
ASSET_NAME = "DT_SemanticIds_EarthCommand"
JSON_PATH = os.path.join(unreal.Paths.project_content_dir(), "Systems", "SemanticIds", ASSET_NAME + ".json")


def main() -> None:
    if not os.path.exists(JSON_PATH):
        raise RuntimeError(f"registry JSON missing: {JSON_PATH}")
    row_struct = unreal.load_object(None, "/Script/OdysseyCore.OdysseySemanticIdRow")
    if row_struct is None:
        raise RuntimeError("FOdysseySemanticIdRow not found: is the OdysseyCore module compiled and loaded?")
    path = f"{ASSET_DIR}/{ASSET_NAME}"
    table = unreal.load_asset(path)
    if table is None:
        factory = unreal.DataTableFactory()
        factory.set_editor_property("struct", row_struct)
        table = unreal.AssetToolsHelpers.get_asset_tools().create_asset(ASSET_NAME, ASSET_DIR, unreal.DataTable, factory)
    if not unreal.DataTableFunctionLibrary.fill_data_table_from_json_file(table, JSON_PATH, row_struct):
        raise RuntimeError("DataTable import failed (see the Output Log)")
    unreal.EditorAssetLibrary.save_loaded_asset(table)
    rows = unreal.DataTableFunctionLibrary.get_data_table_row_names(table)
    unreal.log(f"[Odyssey] {path}: {len(rows)} semantic ids imported")


main()
