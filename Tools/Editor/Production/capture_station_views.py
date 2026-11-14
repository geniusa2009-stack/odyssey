"""Unreal Editor Python: inspection screenshots of the imported station dressing in L_EarthCommand_Slice.

    py "<project>/Tools/Editor/Production/capture_station_views.py"

Moves the level viewport camera through VIEWS, one shot at a time (a Slate tick state machine, so
the viewport renders between shots), writing Saved/Odyssey/StationCapture/<name>.png. The map is not
modified or saved.
"""
import os

import unreal

MAP = "/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice"
OUT = os.path.join(os.path.abspath(unreal.Paths.project_saved_dir()), "Odyssey", "StationCapture")
VIEWS = [  # name, location (cm), (pitch, yaw)
    ("STATION_01_mission_control_holo_table", (1400, 330, 175), (-14, 90)),
    ("STATION_02_training_simulator", (2700, 420, 170), (-8, 90)),
    ("STATION_03_engineering_drone_dock", (2620, -760, 175), (-10, 136)),
    ("STATION_04_engineering_overview", (3080, -330, 330), (-22, -150)),
]
WARM, SETTLE = 240, 90

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
os.makedirs(OUT, exist_ok=True)
les.load_level(MAP)
S = {"i": 0, "wait": WARM, "task": None, "handle": None, "phase": "move"}


def tick(_dt):
    if S["wait"] > 0:
        S["wait"] -= 1
        return
    if S["task"] is not None:
        if not S["task"].is_task_done():
            return
        S["task"] = None
        S["i"] += 1
        S["phase"] = "move"
    if S["i"] >= len(VIEWS):
        unreal.unregister_slate_post_tick_callback(S["handle"])
        unreal.log(f"[OdysseyStationCapture] done -> {OUT}")
        return
    name, loc, (pitch, yaw) = VIEWS[S["i"]]
    if S["phase"] == "move":
        ues.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw))
        S["phase"] = "shoot"
        S["wait"] = SETTLE
        return
    path = os.path.join(OUT, name + ".png")
    S["task"] = unreal.AutomationLibrary.take_high_res_screenshot(1600, 900, path)
    unreal.log(f"[OdysseyStationCapture] {name}")


S["handle"] = unreal.register_slate_post_tick_callback(tick)
