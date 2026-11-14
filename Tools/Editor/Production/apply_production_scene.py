"""Real-editor visual layer. Preserve collision skeleton, semantic actors and backend light groups."""
import unreal, json, os

ROOT='/Game/Earth/EarthCommand/Engineering/Production'
USE_MODULES=globals().get('USE_MODULES',True)
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
eal=unreal.EditorAssetLibrary
actors={a.get_actor_label():a for a in eas.get_all_level_actors()}
FOLDER='EngineeringProduction'

def mat(name):
    if name=='OD_MAT_Display':return unreal.load_asset(ROOT+'/Materials/M_ODY_ProductionDisplay')
    if name=='OD_MAT_Glass':return unreal.load_asset(ROOT+'/Materials/M_ODY_ProductionGlass')
    return unreal.load_asset(ROOT+'/Materials/MI_Prod_'+name.removeprefix('OD_MAT_'))

def equipment(name):
    m=unreal.load_asset(ROOT+'/Equipment/'+name+'/'+name)
    assert m,name
    return m

def set_finish(mesh):
    for i,slot in enumerate(mesh.get_editor_property('static_materials')):
        m=mat(str(slot.material_slot_name))
        if m:mesh.set_material(i,m)
    eal.save_loaded_asset(mesh)

def place(label,mesh,loc,rot):
    assert mesh,label
    a=actors.get(label)
    if a is None:a=eas.spawn_actor_from_class(unreal.StaticMeshActor,loc,rot);actors[label]=a
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_actor_location(loc,False,False)
    a.set_actor_rotation(rot,False)
    a.static_mesh_component.set_static_mesh(mesh)
    a.static_mesh_component.set_editor_property('override_materials',[])
    a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    a.static_mesh_component.set_editor_property('cast_shadow',True)
    a.set_editor_property('tags',[unreal.Name('OdysseyProductionVisual')])
    return a

# Validate resources before changing the level.
names=['OD_ENG_PowerBusB','OD_SYS_ORIONTerminal','OD_SYS_ServerRack','OD_ENV_CeilingLight','OD_ENV_WallUtilityPanel','OD_ENV_VentilationModule','OD_PROP_SupplyCrate']
meshes={n:equipment(n) for n in names}
hero=unreal.load_asset(ROOT+'/ConsoleHero/OD_ENG_PowerConsole_PNG')
architecture=None if USE_MODULES else unreal.load_asset(ROOT+'/Architecture/OD_ENG_Architecture')
plant=None if USE_MODULES else unreal.load_asset(ROOT+'/Architecture/OD_ENG_ServicePlant')
assert hero and (USE_MODULES or (architecture and plant))
assert unreal.load_asset(ROOT+'/Materials/M_ODY_ConsoleHero')
for m in list(meshes.values())+([] if USE_MODULES else [architecture,plant]):set_finish(m)
hero.set_material(0,unreal.load_asset(ROOT+'/Materials/M_ODY_ConsoleHero'))
eal.save_loaded_asset(hero)

with unreal.ScopedEditorTransaction('ODYSSEY Engineering visual production'):
    # Keep the technical collision meshes at the validated poses, with a distinct visible art layer.
    replacements={
        'Sys_PowerBusB':hero,
        'PROXY_PowerBusB_Cabinet':meshes['OD_ENG_PowerBusB'],
        'PROXY_ORION_Terminal_ENG':meshes['OD_SYS_ORIONTerminal'],
        'PROXY_ServerRack_ENG_01':meshes['OD_SYS_ServerRack'],
        'PROXY_ServerRack_ENG_02':meshes['OD_SYS_ServerRack'],
        'PROXY_ServerRack_ENG_03':meshes['OD_SYS_ServerRack'],
        'PROXY_WallUtilityPanel_ENG':meshes['OD_ENV_WallUtilityPanel'],
        'PROXY_VentModule_ENG':meshes['OD_ENV_VentilationModule'],
    }
    for label,mesh in replacements.items():
        original=actors[label]
        c=original.get_component_by_class(unreal.StaticMeshComponent)
        c.set_visibility(False,False)
        original.set_editor_property('tags',list(original.tags)+[unreal.Name('TechnicalCollisionProxy'),unreal.Name('ProductionVisualAttached')])
        rot=original.get_actor_rotation()
        if label=='Sys_PowerBusB':rot=unreal.Rotator(pitch=rot.pitch,yaw=rot.yaw-90,roll=rot.roll)
        place('ART_'+label,mesh,original.get_actor_location(),rot)
    for label in ['Sys_StationBattery','Sys_ThermalPlant','Sys_AirHandling','Sys_WaterSystems','Store_SparesLocker']:
        actors[label].get_component_by_class(unreal.StaticMeshComponent).set_visibility(False,False)
    # Replace the former finish kit; collision shell and semantic volumes remain intact.
    for label,a in actors.items():
        if label.startswith('Kit_ENG_'):
            a.static_mesh_component.set_visibility(False,False)
    if not USE_MODULES:
        place('ART_PressureShellAndServices',architecture,unreal.Vector(2500,-800,0),unreal.Rotator())
        place('ART_EngineeringPlant',plant,unreal.Vector(2500,-800,0),unreal.Rotator())
    crate=place('ART_MaintenanceSupplies',meshes['OD_PROP_SupplyCrate'],unreal.Vector(2020,-430,0),unreal.Rotator(yaw=0))
    crate.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    crate.static_mesh_component.set_collision_profile_name('BlockAll')

    # Reuse the gameplay-aware fixture actor. Its EmissiveScale continues to mirror the real light.
    for i in range(4):
        fixture=actors['Engineering_Light'+str(i)]
        c=fixture.get_component_by_class(unreal.StaticMeshComponent)
        c.set_static_mesh(meshes['OD_ENV_CeilingLight'])
        c.set_editor_property('override_materials',[])
        c.set_editor_property('cast_shadow',True)
        fixture.get_component_by_class(unreal.RectLightComponent).set_editor_property('relative_location',unreal.Vector(0,0,-16))
        light=fixture.get_component_by_class(unreal.RectLightComponent)
        light.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
        light.set_editor_property('intensity',3500.0)

    # Use explicit color keywords: the Color struct constructor has BGRA positional order.
    layout=os.path.join(unreal.Paths.project_content_dir(),'Systems/Greybox/L_EarthCommand_Slice.layout.json')
    with open(layout,encoding='utf-8') as f:data=json.load(f)
    for area in data['areas']:
        for spec in area.get('lights',[]):
            a=actors.get(spec['label'])
            if a:
                c=a.get_component_by_class(unreal.LightComponent)
                if c:
                    r,g,b=spec['color']
                    c.set_editor_property('light_color',unreal.Color(r=int(r*255),g=int(g*255),b=int(b*255),a=255))
                    if spec['label'].startswith('Corridor_Light'):
                        c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
                        c.set_editor_property('intensity',float(spec['intensity']))
    # Preview the normal state; this flag affects the editor only, not backend incident behavior.
    actors['Engineering_Warning'].set_is_temporarily_hidden_in_editor(True)

    pp=actors.get('ART_EngineeringExposure')
    if pp is None:pp=eas.spawn_actor_from_class(unreal.PostProcessVolume,unreal.Vector(2500,-800,250),unreal.Rotator())
    pp.set_actor_label('ART_EngineeringExposure');pp.set_folder_path(FOLDER)
    pp.set_editor_property('unbound',True);pp.set_editor_property('priority',10.0)
    settings=unreal.PostProcessSettings()
    values={'auto_exposure_method':unreal.AutoExposureMethod.AEM_MANUAL,'auto_exposure_apply_physical_camera_exposure':False,'auto_exposure_bias':-5.5,'bloom_intensity':0.18,'vignette_intensity':0.12,'motion_blur_amount':0.0,'scene_fringe_intensity':0.0}
    for key,value in values.items():settings.set_editor_property('override_'+key,True);settings.set_editor_property(key,value)
    pp.set_editor_property('settings',settings)

    # Purposeful identification plates, kept to service zones rather than decorative noise.
    def sign(label,text,location,yaw,size):
        a=actors.get(label)
        if a is None:a=eas.spawn_actor_from_class(unreal.TextRenderActor,unreal.Vector(*location),unreal.Rotator(yaw=yaw))
        a.set_actor_label(label);a.set_folder_path(FOLDER+'/Identification')
        t=a.get_component_by_class(unreal.TextRenderComponent)
        t.set_text(text);t.set_world_size(size)
        t.set_horizontal_alignment(unreal.HorizTextAligment.EHTA_CENTER)
        t.set_text_render_color(unreal.Color(r=42,g=54,b=61,a=255))
    sign('ART_EngineeringIdentification','ENGINEERING',(2500,-254,351),-90,15)
    sign('ART_EngineeringDeckCode','EC / 04    SERVICE ACCESS',(2500,-255,328),-90,4)
    sign('ART_BatteryIdentification','RESERVE POWER',(2500,-1224,195),90,6)
    sign('ART_ThermalIdentification','THERMAL CONTROL',(3000,-1368,361),90,8)
    sign('ART_DistributionIdentification','BUS B / DISTRIBUTION',(1990,-1368,360),90,7)
    for name,x,y in [('ART_BatteryMaintenanceDecal',2500,-1130),('ART_ThermalMaintenanceDecal',2990,-1130)]:
        a=actors.get(name)
        if a is None:a=eas.spawn_actor_from_class(unreal.DecalActor,unreal.Vector(x,y,8),unreal.Rotator(pitch=-90))
        a.set_actor_label(name);a.set_folder_path(FOLDER+'/Identification')
        c=a.get_component_by_class(unreal.DecalComponent)
        c.set_editor_property('decal_size',unreal.Vector(12,115,30))
        c.set_decal_material(unreal.load_asset(ROOT+'/Materials/M_ODY_ServiceDecal'))

unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_invalidate_viewports()
print('VISUAL_LAYER_APPLIED_UNSAVED; render and validate before saving the map')
