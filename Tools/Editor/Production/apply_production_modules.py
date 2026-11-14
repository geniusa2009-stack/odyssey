import unreal,json,os
ROOT='/Game/Earth/EarthCommand/Engineering/Production'
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors={a.get_actor_label():a for a in eas.get_all_level_actors()}
with open(os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork/module_import_report.json')) as f:modules=json.load(f)
assert len(modules)>=10
for label in ['ART_PressureShellAndServices','ART_EngineeringPlant']:
    if label in actors:actors[label].static_mesh_component.set_visibility(False,False)
for entry in modules:
    label='ART_Module_'+entry['name']
    a=actors.get(label)
    if a is None:a=eas.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(2500,-800,0),unreal.Rotator())
    a.set_actor_label(label);a.set_folder_path('EngineeringProduction/Modules/'+entry['folder'])
    a.static_mesh_component.set_static_mesh(unreal.load_asset(entry['path']))
    a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    a.static_mesh_component.set_editor_property('cast_shadow',True)
    a.set_editor_property('tags',[unreal.Name('OdysseyProductionVisual')])
fixture=actors.get('ART_ConsoleTaskFixture')
if fixture is None:fixture=eas.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(2250,-990,325),unreal.Rotator())
fixture.set_actor_label('ART_ConsoleTaskFixture');fixture.set_folder_path('EngineeringProduction/TaskLighting')
fixture.static_mesh_component.set_static_mesh(unreal.load_asset(ROOT+'/Equipment/OD_ENV_CeilingLight/OD_ENV_CeilingLight'))
fixture.set_actor_scale3d(unreal.Vector(0.5,0.5,0.5))
fixture.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
light=actors.get('ART_ConsoleReserveTaskLight')
if light is None:light=eas.spawn_actor_from_class(unreal.RectLight,unreal.Vector(2250,-990,316),unreal.Rotator(pitch=-90))
light.set_actor_label('ART_ConsoleReserveTaskLight');light.set_folder_path('EngineeringProduction/TaskLighting')
c=light.get_component_by_class(unreal.RectLightComponent)
c.set_editor_property('mobility',unreal.ComponentMobility.MOVABLE)
c.set_editor_property('intensity_units',unreal.LightUnits.LUMENS)
c.set_editor_property('intensity',1200.0)
c.set_editor_property('source_width',90.0);c.set_editor_property('source_height',20.0)
c.set_editor_property('attenuation_radius',500.0)
c.set_editor_property('light_color',unreal.Color(r=255,g=246,b=232,a=255))
light.set_editor_property('tags',[unreal.Name('ReserveCircuitTaskLighting')])
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_invalidate_viewports()
print('PRODUCTION_MODULES_APPLIED_UNSAVED')
