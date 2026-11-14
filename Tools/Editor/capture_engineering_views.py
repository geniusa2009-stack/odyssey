"""Unreal Editor Python: render inspection screenshots of the Engineering slice.

Run in a rendering editor session (not -nullrhi):
    UnrealEditor Odyssey.uproject -ExecutePythonScript="<project>/Tools/Editor/capture_engineering_views.py"
Writes PNGs to <project>/Saved/Odyssey/Screenshots/ and quits the editor when done (QUIT = True).
Temporary CameraActors are destroyed afterwards; the map is not saved.
"""
import os

import unreal

QUIT = True
MAP = "/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice"
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Odyssey", "Screenshots")
RES = (1600, 900)
WARMUP_TICKS = 900       # let shaders/distance fields settle before the first capture
BETWEEN_TICKS = 120

# name, location (cm), rotation (pitch, yaw, roll) — world space of the verification map
VIEWS = [
    ("ENG_01_corridor_entrance", (2500, 160, 170), (-4, -90, 0)),
    ("ENG_02_power_console", (2470, -820, 185), (-14, -135, 0)),
    ("ENG_03_overview_ne_corner", (3130, -260, 400), (-20, -140, 0)),
    ("ENG_04_ceiling_services", (2450, -650, 160), (32, -40, 0)),
    ("ENG_05_room_to_door", (2500, -1300, 175), (-3, 90, 0)),
]

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
os.makedirs(OUT, exist_ok=True)
les.load_level(MAP)

state = {"tick": 0, "i": 0, "task": None, "cams": [], "wait": WARMUP_TICKS, "handle": None}


def finish():
    unreal.unregister_slate_post_tick_callback(state["handle"])
    for c in state["cams"]:
        eas.destroy_actor(c)
    unreal.log(f"[Odyssey] Engineering screenshots written to {OUT}")
    if QUIT:
        unreal.SystemLibrary.quit_editor()


def tick(_dt):
    if state["wait"] > 0:
        state["wait"] -= 1
        return
    task = state["task"]
    if task is not None and not task.is_task_done():
        return
    if state["i"] >= len(VIEWS):
        finish()
        return
    name, loc, rot = VIEWS[state["i"]]
    cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]))
    cam.camera_component.set_editor_property("field_of_view", 90.0)
    state["cams"].append(cam)
    path = os.path.join(OUT, name + ".png")
    unreal.SystemLibrary.execute_console_command(None, "r.ScreenPercentage 100")
    state["task"] = unreal.AutomationLibrary.take_high_res_screenshot(RES[0], RES[1], path, camera=cam, delay=2.0)
    unreal.log(f"[Odyssey] capturing {name} at {loc} {rot} -> {path}")
    state["i"] += 1
    state["wait"] = BETWEEN_TICKS


state["handle"] = unreal.register_slate_post_tick_callback(tick)
