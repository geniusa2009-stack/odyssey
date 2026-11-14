"""Sequential real-editor camera captures, keeping technical warning intensity intact."""
import unreal, os, time, json, traceback

OUT=globals().get('OUT',os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionReview'))
RES=globals().get('RES',(1600,900))
VIEWS=globals().get('VIEWS',[
    ('Console_Front',(2335,-945,160),(-18,-135,0),58),
    ('Console_Rear',(1985,-1295,160),(-18,45,0),58),
])
os.makedirs(OUT,exist_ok=True)
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
warning=next(a for a in eas.get_all_level_actors() if a.get_actor_label()=='Engineering_Warning')
wc=warning.get_component_by_class(unreal.PointLightComponent)
base=wc.get_editor_property('intensity');wc.set_editor_property('intensity',0.0)
state={'i':0,'task':None,'camera':None,'start':None,'handle':None,'due':time.monotonic()+5,'completed':[]}
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_set_viewport_realtime(True)
unreal.SystemLibrary.execute_console_command(None,'r.HighResScreenshotDelay 4')

def status(done=False,error=None):
    with open(os.path.join(OUT,'views_status.json'),'w') as f:json.dump({'done':done,'error':error,'completed':state['completed'],'expected':[v[0] for v in VIEWS]},f)

def finish(error=None):
    unreal.unregister_slate_post_tick_callback(state['handle'])
    if state['camera'] and unreal.is_valid(state['camera']):eas.destroy_actor(state['camera'])
    wc.set_editor_property('intensity',base)
    status(done=error is None,error=error)

def capture_tick(dt):
    try:
        if time.monotonic()<state['due']:return
        if state['task'] is not None:
            if not state['task'].is_task_done():
                if time.monotonic()-state['start']>240:finish('Screenshot task timeout')
                return
            state['completed'].append(VIEWS[state['i']][0])
            eas.destroy_actor(state['camera']);state['camera']=None
            state['task']=None;state['i']+=1;status()
        if state['i']>=len(VIEWS):finish();return
        name,location,rotation,fov=VIEWS[state['i']]
        camera=eas.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(*location),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
        camera.set_actor_label('TEMP_Capture_'+name)
        camera.camera_component.set_editor_property('field_of_view',float(fov))
        state['camera']=camera;state['start']=time.monotonic()
        state['task']=unreal.AutomationLibrary.take_high_res_screenshot(RES[0],RES[1],os.path.join(OUT,name+'.png'),camera=camera,delay=12.0,force_game_view=True)
    except Exception:finish(traceback.format_exc())

state['handle']=unreal.register_slate_post_tick_callback(capture_tick)
status()
print('VIEWS_SCHEDULED',OUT,[v[0] for v in VIEWS])
