"""Isolated static assembly imports; original articulated GLBs remain untouched."""
import unreal, os, json

base = os.path.join(unreal.Paths.project_dir(), 'ArtSource/OdysseyAssetPack/GLB')
destination = '/Game/Earth/EarthCommand/Engineering/Production/Equipment'
assets = ['OD_ENG_PowerBusB', 'OD_SYS_ORIONTerminal', 'OD_SYS_ServerRack', 'OD_ENV_CeilingLight', 'OD_ENV_WallUtilityPanel', 'OD_ENV_VentilationModule', 'OD_PROP_SupplyCrate']
report = {}
for name in assets:
    path = destination + '/' + name + '/' + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        objects = [unreal.load_asset(path)]
    else:
        pipeline = unreal.InterchangeGenericAssetsPipeline()
        pipeline.common_meshes_properties.set_editor_property('bake_meshes', True)
        pipeline.mesh_pipeline.set_editor_property('combine_static_meshes_behavior', unreal.InterchangeCombineStaticMeshesBehavior.ALL)
        pipeline.mesh_pipeline.set_editor_property('collision', False)
        stack = unreal.InterchangePipelineStackOverride()
        stack.set_editor_property('override_pipelines', [unreal.SoftObjectPath(pipeline.get_path_name())])
        task = unreal.AssetImportTask()
        for key, value in {'filename': os.path.join(base, name+'.glb'), 'destination_path': destination+'/'+name, 'automated': True, 'replace_existing': False, 'save': True, 'async_': False, 'options': stack}.items():
            task.set_editor_property(key, value)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        objects = task.get_objects()
    meshes = [o for o in objects if isinstance(o, unreal.StaticMesh)]
    assert len(meshes) == 1, (name, meshes)
    m = meshes[0]
    bb = m.get_bounding_box()
    size = bb.max - bb.min
    assert min(size.x, size.y, size.z) > 1, (name, bb)
    sme = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    sme.remove_collisions(m)
    if name != 'OD_ENV_CeilingLight':
        sme.add_simple_collisions(m, unreal.ScriptCollisionShapeType.BOX)
    unreal.EditorAssetLibrary.save_loaded_asset(m)
    report[name] = {'path': m.get_path_name(), 'bounds': str(bb), 'slots': [str(s.material_slot_name) for s in m.static_materials]}
    print('VALIDATED', name, report[name])
print('PACK_IMPORT_COMPLETE',json.dumps(report))
