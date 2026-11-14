"""Run Engineering after the worker resets PIE; preserve the actual automation result."""
import unreal,time,os,json,re
les=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not les.is_in_play_in_editor(), 'End PIE before launching the validation session.'
cmd=unreal.SystemLibrary.get_command_line()
m=re.search(r'(?i)-(?:abslog|log)=(?:"([^"]+)"|(\S+))',cmd)
log=os.path.abspath((m.group(1) or m.group(2)) if m else os.path.join(unreal.Paths.project_log_dir(),'Odyssey.log'))
assert os.path.isfile(log), 'Cannot locate the current editor log; launch the editor with -abslog=<file>.'
out=os.path.join(unreal.Paths.project_saved_dir(),'Odyssey/ProductionWork/gameplay_status.json')
os.makedirs(os.path.dirname(out),exist_ok=True)
state={'start':time.monotonic(),'offset':os.path.getsize(log),'handle':None,'begun':False}
def wait_for_worker(dt):
    with open(log,errors='replace') as f:f.seek(state['offset']);events=f.read()
    if not state['begun'] and 'Received RunTests Engineering' in events:
        les.editor_request_begin_play();state['begun']=True
    finished='Test Completed. Result=' in events
    expired=time.monotonic()-state['start']>1000
    if finished or expired:
        unreal.unregister_slate_post_tick_callback(state['handle'])
        with open(out,'w') as f:json.dump({'done':finished,'pie_requested':state['begun'],'timeout':expired,'events':events[events.rfind('Test Completed. Result='):] if finished else ''},f,indent=2)
state['handle']=unreal.register_slate_post_tick_callback(wait_for_worker)
unreal.SystemLibrary.execute_console_command(None,'Automation RunTests Odyssey.Slice.Engineering')
print('Engineering validation queued; no framerate prerequisite bypassed.')
