import unreal,os
root="/Game/Earth/EarthCommand/Engineering/Production"
p=unreal.InterchangeGenericAssetsPipeline()
p.common_meshes_properties.set_editor_property("bake_meshes",True)
p.mesh_pipeline.set_editor_property("combine_static_meshes_behavior",unreal.InterchangeCombineStaticMeshesBehavior.ALL)
p.mesh_pipeline.set_editor_property("collision",False)
p.material_pipeline.set_editor_property("import_materials",False)
s=unreal.InterchangePipelineStackOverride();s.set_editor_property("override_pipelines",[unreal.SoftObjectPath(p.get_path_name())])
t=unreal.AssetImportTask()
for k,v in {"filename":os.path.join(unreal.Paths.project_dir(),"ArtSource/OdysseyProduction/OD_ENG_PowerConsole_Clean.glb"),"destination_path":root+"/ConsoleClean","automated":True,"replace_existing":True,"save":False,"options":s}.items():t.set_editor_property(k,v)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
meshes=[o for o in t.get_objects() if isinstance(o,unreal.StaticMesh)]
assert len(meshes)==1
m=meshes[0]
for i,slot in enumerate(m.static_materials):
 n=str(slot.material_slot_name)
 material=unreal.load_asset(root+"/Materials/"+("M_ODY_ProductionDisplay" if n.startswith("OD_MAT_Screen_") or n=="OD_MAT_Display" else "MI_Prod_"+n.removeprefix("OD_MAT_")))
 assert material,n
 m.set_material(i,material)
unreal.EditorAssetLibrary.save_loaded_asset(m)
print("CLEAN_CONSOLE",m.get_path_name(),m.get_bounding_box(),[str(s.material_slot_name) for s in m.static_materials])
