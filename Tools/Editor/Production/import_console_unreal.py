"""Run in the live Unreal Editor: isolated production import, no level changes."""
import unreal, json, os

source = os.path.join(unreal.Paths.project_dir(), 'ArtSource/OdysseyProduction/OD_ENG_PowerConsole_PNG.glb')
mesh_path='/Game/Earth/EarthCommand/Engineering/Production/ConsoleHero/OD_ENG_PowerConsole_PNG'
if unreal.EditorAssetLibrary.does_asset_exist(mesh_path) and not globals().get('FORCE_REIMPORT',False):
    objects=[unreal.load_asset(mesh_path)]
else:
    pipeline = unreal.InterchangeGenericAssetsPipeline()
    pipeline.common_meshes_properties.set_editor_property('bake_meshes', True)
    pipeline.common_meshes_properties.set_editor_property('recompute_normals', False)
    pipeline.mesh_pipeline.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
    pipeline.mesh_pipeline.set_editor_property('build_nanite', True)
    pipeline.mesh_pipeline.set_editor_property('collision', False)
    stack = unreal.InterchangePipelineStackOverride()
    stack.set_editor_property('override_pipelines', [unreal.SoftObjectPath(pipeline.get_path_name())])
    task = unreal.AssetImportTask()
    for key, value in {'filename': source, 'destination_path': '/Game/Earth/EarthCommand/Engineering/Production/ConsoleHero', 'automated': True, 'replace_existing': True, 'save': True, 'async_': False, 'options': stack}.items():
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    objects=task.get_objects()

meshes = []
for obj in objects:
    print('IMPORTED', obj.get_path_name(), obj.get_class().get_name())
    if isinstance(obj, unreal.StaticMesh):
        bb = obj.get_bounding_box()
        print('BOUNDS', bb)
        print('MATERIALS', [(str(m.material_slot_name), str(m.material_interface)) for m in obj.static_materials])
        print('NANITE', obj.get_editor_property('nanite_settings'))
        sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        if sme.get_simple_collision_count(obj)==0:
            sme.add_simple_collisions(obj, unreal.ScriptCollisionShapeType.BOX)
        unreal.EditorAssetLibrary.save_loaded_asset(obj)
        meshes.append(obj.get_path_name())
assert len(meshes) == 1, meshes
print('CONSOLE_IMPORT_OK', meshes)
