import unreal,os
ROOT='/Game/Earth/EarthCommand/Engineering/Production'
PROJECT=unreal.Paths.project_dir()
at=unreal.AssetToolsHelpers.get_asset_tools();eal=unreal.EditorAssetLibrary;mel=unreal.MaterialEditingLibrary
for n in ['T_ODY_ConsoleLeft','T_ODY_ConsoleRight']:
    if not eal.does_asset_exist(ROOT+'/Textures/'+n):
        t=unreal.AssetImportTask()
        for k,v in {'filename':os.path.join(PROJECT,'Tools/Editor/Production/surface_textures',n+'.png'),'destination_path':ROOT+'/Textures','automated':True,'save':True}.items():t.set_editor_property(k,v)
        at.import_asset_tasks([t])
path=ROOT+'/Materials/M_ODY_ConsoleLCD'
if not eal.does_asset_exist(path):
    m=at.create_asset('M_ODY_ConsoleLCD',ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    tex=mel.create_material_expression(m,unreal.MaterialExpressionTextureSampleParameter2D)
    tex.set_editor_property('parameter_name','ScreenGraphic');tex.set_editor_property('texture',unreal.load_asset(ROOT+'/Textures/T_ODY_EngineeringDisplay'))
    mel.connect_material_property(tex,'',unreal.MaterialProperty.MP_BASE_COLOR)
    r=mel.create_material_expression(m,unreal.MaterialExpressionConstant);r.set_editor_property('r',0.14);mel.connect_material_property(r,'',unreal.MaterialProperty.MP_ROUGHNESS)
    strength=mel.create_material_expression(m,unreal.MaterialExpressionScalarParameter);strength.set_editor_property('parameter_name','EmissiveScale');strength.set_editor_property('default_value',40.0)
    mul=mel.create_material_expression(m,unreal.MaterialExpressionMultiply)
    mel.connect_material_expressions(tex,'',mul,'A');mel.connect_material_expressions(strength,'',mul,'B');mel.connect_material_property(mul,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m);eal.save_loaded_asset(m)
master=unreal.load_asset(path);screens={}
for suffix,texture in [('Main','T_ODY_EngineeringDisplay'),('Left','T_ODY_ConsoleLeft'),('Right','T_ODY_ConsoleRight')]:
    path=ROOT+'/Materials/MI_ConsoleScreen_'+suffix
    mi=unreal.load_asset(path) if eal.does_asset_exist(path) else at.create_asset('MI_ConsoleScreen_'+suffix,ROOT+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi,master);mel.set_material_instance_texture_parameter_value(mi,'ScreenGraphic',unreal.load_asset(ROOT+'/Textures/'+texture));eal.save_loaded_asset(mi);screens[suffix]=mi
mesh=unreal.load_asset(ROOT+'/ConsoleClean/OD_ENG_PowerConsole_Clean');assert mesh
for i,slot in enumerate(mesh.static_materials):
    name=str(slot.material_slot_name)
    if name.startswith('OD_MAT_Screen_'):mesh.set_material(i,screens[name.removeprefix('OD_MAT_Screen_')])
eal.save_loaded_asset(mesh)
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);actors={a.get_actor_label():a for a in eas.get_all_level_actors()}
a=actors['ART_Sys_PowerBusB'];a.static_mesh_component.set_static_mesh(mesh);a.static_mesh_component.set_editor_property('override_materials',[]);a.set_actor_rotation(actors['Sys_PowerBusB'].get_actor_rotation(),False)
for label,text,z,size in [('ART_ConsoleBrand','ODYSSEY',35,6),('ART_ConsoleIdentity','POWER DISTRIBUTION / EC-04',28,1.5)]:
    t=actors.get(label)
    if t is None:t=eas.spawn_actor_from_class(unreal.TextRenderActor,unreal.Vector(2178,-1102,z),unreal.Rotator(yaw=45))
    t.set_actor_label(label);t.set_folder_path('EngineeringProduction/Identification')
    c=t.get_component_by_class(unreal.TextRenderComponent);c.set_text(text);c.set_world_size(size);c.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER);c.set_text_render_color(unreal.Color(r=40,g=51,b=57,a=255))
print('CLEAN_CONSOLE_APPLIED')
