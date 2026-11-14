"""Split the authored finish into Lumen-friendly modules; preserve its shared authoring origin."""
import unreal, os, json
ROOT='/Game/Earth/EarthCommand/Engineering/Production'
eal=unreal.EditorAssetLibrary
at=unreal.AssetToolsHelpers.get_asset_tools()
sme=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
os.makedirs(os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork'),exist_ok=True)
report=[]
for filename,folder in [('OD_ENG_Architecture','Architecture'),('OD_ENG_ServicePlant','Plant')]:
    pipeline=unreal.InterchangeGenericAssetsPipeline()
    pipeline.common_meshes_properties.set_editor_property('bake_meshes',True)
    pipeline.mesh_pipeline.set_editor_property('combine_static_meshes_behavior',unreal.InterchangeCombineStaticMeshesBehavior.DO_NOT_COMBINE)
    pipeline.mesh_pipeline.set_editor_property('collision',False)
    pipeline.material_pipeline.set_editor_property('import_materials',False)
    stack=unreal.InterchangePipelineStackOverride()
    stack.set_editor_property('override_pipelines',[unreal.SoftObjectPath(pipeline.get_path_name())])
    task=unreal.AssetImportTask()
    for k,v in {'filename':os.path.join(unreal.Paths.project_dir(),'ArtSource/OdysseyProduction',filename+'.glb'),'destination_path':ROOT+'/Modules/'+folder,'automated':True,'replace_existing':True,'save':False,'async_':False,'options':stack}.items():task.set_editor_property(k,v)
    at.import_asset_tasks([task])
    meshes=[m for m in task.get_objects() if isinstance(m,unreal.StaticMesh)]
    assert len(meshes)>=5,(filename,meshes)
    for m in meshes:
        settings=sme.get_lod_build_settings(m,0)
        settings.set_editor_property('max_lumen_mesh_cards',32)
        settings.set_editor_property('distance_field_resolution_scale',1.5)
        sme.set_lod_build_settings(m,0,settings)
        for i,slot in enumerate(m.get_editor_property('static_materials')):
            n=str(slot.material_slot_name).removeprefix('OD_MAT_')
            material=unreal.load_asset(ROOT+'/Materials/MI_Prod_'+n)
            assert material,n
            m.set_material(i,material)
        eal.save_loaded_asset(m)
        report.append({'name':m.get_name(),'path':m.get_path_name(),'folder':folder,'bounds':str(m.get_bounding_box()),'lumen_cards':32})
        print('MODULE_READY',m.get_path_name())
with open(os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork/module_import_report.json'),'w') as f:json.dump(report,f,indent=2)
print('PRODUCTION_MODULES_READY',len(report))
