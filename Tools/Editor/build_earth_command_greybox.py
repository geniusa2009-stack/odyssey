"""Unreal Editor Python: build the Earth Command vertical-slice greybox.

UNREAL_EDITOR_VERIFICATION_REQUIRED — written for UE 5.8 editor scripting; NOT yet run. Nothing
produced by this script is part of the repository until a human has reviewed it in the editor
(Phase 6 §33: AI-generated editor work is experimental until reviewed).

EXACT TARGET (§33) — the only asset this script creates or modifies:
    /Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice
All actors it spawns live in that map under the World Outliner folder "EarthCommandGreybox/…".
It refuses to touch an existing map unless REBUILD = True, and then deletes only actors inside
"EarthCommandGreybox/".

Areas (Docs/EARTH_COMMAND_GREYBOX.md): Observation Deck, Main Corridor, Mission Control,
Engineering, Hangar entrance. Main Corridor has no backend location (pure Unreal traversal space).

Run inside the editor (after compiling the C++ modules and importing the registry):
    py "<project>/Tools/Editor/build_earth_command_greybox.py"
"""

import unreal

MAP_PATH = "/Game/Earth/EarthCommand/Maps/L_EarthCommand_Slice"
ROOT_FOLDER = "EarthCommandGreybox"
REBUILD = False
# The backend also accepts a load-shedding strategy for the power incident that needs the Training
# and Laboratory rooms (earth.command.training.simulator / laboratory.sample_analyzer). The Phase 6
# brief lists only five areas, so these door-sized stubs are OFF unless the project decides otherwise.
INCLUDE_LOAD_SHED_STUBS = False

E = "earth.command."
CUBE = "/Engine/BasicShapes/Cube.Cube"
CYLINDER = "/Engine/BasicShapes/Cylinder.Cylinder"
WALL = 20.0        # cm
CORRIDOR_H = 320.0
ROOM_H = 420.0

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def v(x, y, z):
    return unreal.Vector(float(x), float(y), float(z))


def place(cls, label, folder, loc, yaw=0.0):
    actor = eas.spawn_actor_from_class(cls, loc, unreal.Rotator(0.0, 0.0, float(yaw)))
    actor.set_actor_label(label)
    actor.set_folder_path(f"{ROOT_FOLDER}/{folder}")
    return actor


def block(label, folder, center, size, mesh=CUBE):
    """A greybox block: size in cm (the engine cube is 100 cm)."""
    a = place(unreal.StaticMeshActor, label, folder, center)
    a.static_mesh_component.set_static_mesh(unreal.load_asset(mesh))
    a.set_actor_scale3d(v(size[0] / 100.0, size[1] / 100.0, size[2] / 100.0))
    return a


def room(name, x0, x1, y0, y1, h, doors):
    """Floor, ceiling and four walls; doors = {side: [(centre, width), ...]} with side in N S E W."""
    folder = f"{name}/Shell"
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    block(f"{name}_Floor", folder, v(cx, cy, -WALL / 2), (x1 - x0, y1 - y0, WALL))
    block(f"{name}_Ceiling", folder, v(cx, cy, h + WALL / 2), (x1 - x0, y1 - y0, WALL))

    def wall(side, a0, a1, fixed):
        cuts = sorted(doors.get(side, []))
        start = a0
        segments = []
        for centre, width in cuts:
            segments.append((start, centre - width / 2))
            start = centre + width / 2
        segments.append((start, a1))
        for i, (s, e) in enumerate(segments):
            if e - s < 1:
                continue
            if side in ("N", "S"):
                block(f"{name}_Wall{side}{i}", folder, v((s + e) / 2, fixed, h / 2), (e - s, WALL, h))
            else:
                block(f"{name}_Wall{side}{i}", folder, v(fixed, (s + e) / 2, h / 2), (WALL, e - s, h))
        for centre, width in cuts:  # lintel above each door (doors are 260 cm high)
            if side in ("N", "S"):
                block(f"{name}_Lintel{side}", folder, v(centre, fixed, (h + 260) / 2), (width, WALL, h - 260))
            else:
                block(f"{name}_Lintel{side}", folder, v(fixed, centre, (h + 260) / 2), (WALL, width, h - 260))

    wall("N", x0, x1, y1)
    wall("S", x0, x1, y0)
    wall("E", y0, y1, x1)
    wall("W", y0, y1, x0)


def bind(actor, semantic_id):
    comp = actor.get_component_by_class(unreal.OdysseySemanticBindingComponent)
    comp.set_editor_property("semantic_id", semantic_id)
    return actor


def anchor(location_id, label, folder, loc, yaw):
    return bind(place(unreal.OdysseySemanticAnchor, label, folder, loc, yaw), location_id)


def zone(location_id, label, folder, center, extent):
    z = bind(place(unreal.OdysseySemanticZone, label, folder, center), location_id)
    z.get_component_by_class(unreal.BoxComponent).set_box_extent(extent, False)
    return z


def system(semantic_id, label, folder, loc, size, yaw=0.0, presented=None, mesh=CUBE):
    a = bind(place(unreal.OdysseySystemActor, label, folder, loc, yaw), semantic_id)
    body = a.get_component_by_class(unreal.StaticMeshComponent)
    body.set_static_mesh(unreal.load_asset(mesh))
    a.set_actor_scale3d(v(size[0] / 100.0, size[1] / 100.0, size[2] / 100.0))
    if presented:
        a.get_component_by_class(unreal.OdysseyInteractableComponent).set_editor_property(
            "presented_actions", [unreal.Name(p) for p in presented])
    return a


def light(label, folder, loc, intensity=4000.0, radius=900.0, color=(1.0, 0.96, 0.9)):
    l = place(unreal.PointLight, label, folder, loc)
    c = l.get_component_by_class(unreal.PointLightComponent)
    c.set_editor_property("intensity", intensity)
    c.set_editor_property("attenuation_radius", radius)
    c.set_editor_property("light_color", unreal.Color(int(color[0] * 255), int(color[1] * 255), int(color[2] * 255), 255))
    return l


def prepare_map():
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        if not REBUILD:
            raise RuntimeError(f"{MAP_PATH} exists; set REBUILD = True to rebuild its greybox folder only")
        les.load_level(MAP_PATH)
        for a in eas.get_all_level_actors():
            if str(a.get_folder_path()).startswith(ROOT_FOLDER):
                eas.destroy_actor(a)
    else:
        les.new_level(MAP_PATH)


def build():
    prepare_map()

    # ---------------------------------------------------------------- Main Corridor (x 0..4000)
    north_doors = [(1400, 240)] + ([(3600, 200)] if INCLUDE_LOAD_SHED_STUBS else [])
    room("MainCorridor", 0, 4000, -200, 200, CORRIDOR_H,
         {"W": [(0, 300)], "E": [(0, 300)], "N": north_doors, "S": [(2500, 240)]})
    for i, x in enumerate(range(400, 4000, 800)):
        light(f"Corridor_Light{i}", "MainCorridor/Lights", v(x, 0, CORRIDOR_H - 40), 2500, 700)
    place(unreal.PlayerStart, "PlayerStart_Fallback", "MainCorridor", v(200, 0, 100))

    # ---------------------------------------------------------------- Observation Deck (west)
    room("ObservationDeck", -1600, 0, -900, 900, 600, {"E": [(0, 300)], "W": [(0, 1400)]})  # W = window opening
    anchor(E + "observation_deck", "Anchor_ObservationDeck", "ObservationDeck", v(-500, 0, 0), 180)
    zone(E + "observation_deck", "Zone_ObservationDeck", "ObservationDeck", v(-800, 0, 200), v(780, 880, 200))
    system(E + "observation_deck.lunar_telescope", "Sys_LunarTelescope", "ObservationDeck", v(-1250, 300, 120), (80, 80, 240),
           presented=["system.inspect"], mesh=CYLINDER)
    system(E + "player_kit", "Store_PlayerKit", "ObservationDeck", v(-300, -700, 50), (120, 60, 100))
    light("ObsDeck_Light", "ObservationDeck/Lights", v(-800, 0, 560), 3000, 1400, (0.85, 0.9, 1.0))

    # ---------------------------------------------------------------- Mission Control (north of corridor)
    room("MissionControl", 800, 2000, 200, 1400, ROOM_H, {"S": [(1400, 240)]})
    anchor(E + "mission_control", "Anchor_MissionControl", "MissionControl", v(1400, 450, 0), 90)
    zone(E + "mission_control", "Zone_MissionControl", "MissionControl", v(1400, 800, 200), v(580, 580, 200))
    system(E + "mission_control.consoles", "Sys_Consoles", "MissionControl", v(1400, 1150, 60), (800, 120, 120),
           presented=["system.inspect"])
    light("MissionControl_Light", "MissionControl/Lights", v(1400, 800, ROOM_H - 40), 3500, 1000)

    # ---------------------------------------------------------------- Engineering (south of corridor)
    room("Engineering", 1800, 3200, -1600, -200, ROOM_H, {"N": [(2500, 240)]})
    anchor(E + "engineering", "Anchor_Engineering", "Engineering", v(2500, -450, 0), -90)
    zone(E + "engineering", "Zone_Engineering", "Engineering", v(2500, -900, 200), v(680, 680, 200))
    console = bind(place(unreal.OdysseyPowerConsole, "Sys_PowerBusB", "Engineering", v(2500, -1000, 0), 90),
                   E + "engineering.power_bus_b")
    console.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(unreal.load_asset(CUBE))
    console.set_actor_scale3d(v(1.6, 0.5, 1.3))
    system(E + "engineering.station_battery", "Sys_StationBattery", "Engineering", v(2000, -1400, 100), (240, 120, 200),
           presented=["system.inspect", "power.reroute"])
    system(E + "engineering.thermal_plant", "Sys_ThermalPlant", "Engineering", v(3000, -1400, 150), (240, 160, 300),
           presented=["system.inspect"])
    system(E + "engineering.air_handling", "Sys_AirHandling", "Engineering", v(3050, -700, 120), (100, 240, 240),
           presented=["system.inspect"])
    system(E + "engineering.water_systems", "Sys_WaterSystems", "Engineering", v(3050, -350, 100), (100, 160, 200),
           presented=["system.inspect"])
    system(E + "engineering.spares_locker", "Store_SparesLocker", "Engineering", v(1900, -700, 110), (80, 160, 220))
    eng_lights = [light(f"Engineering_Light{i}", "Engineering/Lights", v(x, y, ROOM_H - 40), 3500, 900)
                  for i, (x, y) in enumerate([(2150, -550), (2850, -550), (2150, -1250), (2850, -1250)])]
    warn = light("Engineering_Warning", "Engineering/Lights", v(2500, -1150, 260), 0, 600, (1.0, 0.25, 0.1))
    warn.get_component_by_class(unreal.PointLightComponent).component_tags = [unreal.Name("OdysseyWarning")]
    # Engineering ceiling lights follow power bus B (backend power/status) — the world reacts.
    pres = console.get_component_by_class(unreal.OdysseyObjectPresentationComponent)
    pres.set_editor_property("extra_light_actors", eng_lights + [warn])

    # ---------------------------------------------------------------- Hangar entrance (east)
    room("HangarEntrance", 4000, 4800, -600, 600, 500, {"W": [(0, 300)], "E": [(0, 800)]})
    anchor(E + "hangar", "Anchor_Hangar", "HangarEntrance", v(4300, 0, 0), 0)
    zone(E + "hangar", "Zone_Hangar", "HangarEntrance", v(4400, 0, 200), v(380, 580, 200))
    block("Hangar_Floor", "HangarEntrance/Shell", v(6200, 0, -10), (2800, 2400, 20))
    system(E + "hangar.luna01", "Sys_Luna01", "HangarEntrance", v(6400, 0, 350), (900, 450, 700),
           presented=["system.inspect", "mission.authorize"])
    light("Hangar_Light", "HangarEntrance/Lights", v(6000, 0, 1100), 20000, 3000, (0.9, 0.95, 1.0))

    if INCLUDE_LOAD_SHED_STUBS:
        room("TrainingStub", 3300, 3900, 200, 800, CORRIDOR_H, {"S": [(3600, 200)]})
        zone(E + "training", "Zone_Training", "TrainingStub", v(3600, 500, 160), v(280, 280, 160))
        anchor(E + "training", "Anchor_Training", "TrainingStub", v(3600, 350, 0), 90)
        system(E + "training.simulator", "Sys_TrainingSimulator", "TrainingStub", v(3600, 650, 100), (200, 120, 200),
               presented=["system.inspect", "system.set_mode"])

    # ---------------------------------------------------------------- crew placeholders
    for crew, (x, y, yaw) in {"maya": (1400, 900, 90), "omar": (2300, -1000, 0), "sofia": (4500, 300, 0), "jay": (-900, 400, 180)}.items():
        bind(place(unreal.OdysseyCrewPlaceholder, f"Crew_{crew.capitalize()}", "Crew", v(x, y, 100), yaw), crew)

    sky = place(unreal.SkyLight, "SkyLight", "Lighting", v(0, 0, 2000))
    sky.get_component_by_class(unreal.SkyLightComponent).set_editor_property("intensity", 0.3)

    les.save_current_level()
    unreal.log(f"[Odyssey] greybox written to {MAP_PATH} — review before committing (§33)")


build()
