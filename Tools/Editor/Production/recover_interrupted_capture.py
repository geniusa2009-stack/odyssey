"""Run in a responsive, unlocked editor. Restore authored warning state and release only ODYSSEY temporary capture cameras."""
import unreal,os,json,gc,types
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world and "L_EarthCommand_Slice" in world.get_path_name(), "Load the ODYSSEY slice before capture recovery."
les=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert not les.is_in_play_in_editor(), "End PIE before recovering editor capture state."
for obj in gc.get_objects():
    if isinstance(obj,types.FunctionType) and os.path.basename(obj.__code__.co_filename) in ["capture_production_review.py","capture_views_unreal.py"]:
        state=obj.__globals__.get("state",{})
        if state.get("handle"):
            try:unreal.unregister_slate_post_tick_callback(state["handle"])
            except Exception:pass
les.eject_pilot_level_actor()
unreal.SystemLibrary.execute_console_command(None,"r.HighResScreenshotDelay 4")
with open(os.path.join(unreal.Paths.project_content_dir(),"Systems/Greybox/L_EarthCommand_Slice.layout.json"),encoding="utf-8") as f:layout=json.load(f)
intensity=next(l["intensity"] for a in layout["areas"] for l in a.get("lights",[]) if l["label"]=="Engineering_Warning")
eas=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in eas.get_all_level_actors():
    label=a.get_actor_label()
    if label=="Engineering_Warning":a.get_component_by_class(unreal.PointLightComponent).set_editor_property("intensity",float(intensity))
    if label=="TEMP_ProductionReviewCamera" or label.startswith("TEMP_Capture_"):eas.destroy_actor(a)
les.editor_set_viewport_realtime(True)
les.editor_invalidate_viewports()
print("ODYSSEY capture cleanup complete; map not saved.")
