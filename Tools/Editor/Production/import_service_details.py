"""Split the authored finish into Lumen-friendly modules; preserve its shared authoring origin."""
import unreal, os, json
ROOT='/Game/Earth/EarthCommand/Engineering/Production'
eal=unreal.EditorAssetLibrary
at=unreal.AssetToolsHelpers.get_asset_tools()
sme=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
os.makedirs(os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork'),exist_ok=True)
report=[]
for filename,folder in [('OD_ENG_ServiceDetails','Services')]:
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
with open(os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork/details_import_report.json'),'w') as f:json.dump(report,f,indent=2)
print('PRODUCTION_MODULES_READY',len(report))

eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors={a.get_actor_label():a for a in eas.get_all_level_actors()}
for entry in report:
    label='ART_Module_'+entry['name']
    a=actors.get(label)
    if a is None:a=eas.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(2500,-800,0),unreal.Rotator())
    a.set_actor_label(label);a.set_folder_path('EngineeringProduction/ServiceDetails')
    a.static_mesh_component.set_static_mesh(unreal.load_asset(entry['path']))
    a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    a.set_editor_property('tags',[unreal.Name('OdysseyProductionVisual')])
for label,text,loc,yaw in [
 ('ART_Label_Distribution','EC-04  /  ELECTRICAL DISTRIBUTION',(2160,-1360,441),90),
 ('ART_Label_Coolant','COOLANT  /  SUPPLY + RETURN',(1854,-1040,213),0),
 ('ART_Label_Inspection','SERVICE ACCESS  /  02',(2960,-1354,173),90),
 ('ART_Label_PressureHatch','PRESSURE LINER  /  INSPECTION',(1848,-730,174),0)]:
    a=actors.get(label)
    if a is None:a=eas.spawn_actor_from_class(unreal.TextRenderActor,unreal.Vector(*loc),unreal.Rotator(yaw=yaw))
    a.set_actor_label(label);a.set_folder_path('EngineeringProduction/Identification')
    c=a.get_component_by_class(unreal.TextRenderComponent);c.set_text(text);c.set_world_size(3.0)
    c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
    c.set_text_render_color(unreal.Color(r=45,g=52,b=58,a=255))
print('SERVICE_DETAIL_LAYER_APPLIED')
