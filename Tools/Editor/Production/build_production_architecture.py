"""ODYSSEY Engineering authored finish assemblies, in cm around room origin (2500,-800,0).

Uses the installed ODYSSEY asset pack's beveled hard-surface mesh authoring library.
Structural collision and semantic gameplay actors remain in Unreal.
"""
from pathlib import Path
import sys, json

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT/'ArtSource/OdysseyAssetPack/Source'))
from od_core import Node, cbox, cyl, tube
from od_gltf import WHITE, GRAPHITE, GUNMETAL, ALU, RUBBER, ION, HAZARD, write_glb, validate_glb

with open(PROJECT/'Content/Systems/Greybox/L_EarthCommand_Slice.layout.json',encoding='utf-8') as f:
    layout=json.load(f)
engineering=next(a for a in layout['areas'] if a['id']=='engineering')
assert engineering['bounds']==[1800,3200,-1400,-200] and engineering['height']==500, 'Engineering layout changed: update the authored finish before rebuilding.'

OUT = PROJECT/'ArtSource/OdysseyProduction'
OUT.mkdir(parents=True, exist_ok=True)

def box(n, mat, center, size, bevel=0.6):
    n.add(cbox(mat, center, size, bevel=min(bevel,min(size)*0.2)))

root=Node('OD_ENG_Architecture')
walls=root.child('SouthPressureLiner')
# South service wall: a low equipment band and high pressure-shell liner.
for i,(x,w) in enumerate([(-510,330),(-170,330),(170,330),(510,330)]):
    box(walls,WHITE,(x,-576,345),(w,12,210),1.6)
    box(walls,GUNMETAL,(x,-566,231),(w-10,7,8),0.8)
    box(walls,GRAPHITE,(x,-580,112),(w,18,208),1)
    for dx in [-w/2+13,w/2-13]:
        walls.add(cyl(ALU,(x+dx,-568,420),1.5,0.8,'y',12,0.2))
# West wall uses narrow removable service panels around the distribution equipment.
walls=root.child('WestPressureLiner')
for y,h,z in [(-390,250,340),(-85,250,340),(230,280,340),(465,150,340)]:
    box(walls,WHITE,(-677,y,z),(12,h,210),1.6)
    box(walls,GUNMETAL,(-665,y,228),(7,h-8,9),0.7)
    box(walls,GRAPHITE,(-679,y,100),(18,h,190),1)
# East wall is intentionally more mechanical, with recessed plant service enclosures.
walls=root.child('EastPressureLiner')
for y,w in [(-420,300),(-70,360),(330,360)]:
    box(walls,WHITE,(677,y,370),(12,w,160),1.5)
    box(walls,GUNMETAL,(670,y,270),(9,w-10,28),0.8)
    box(walls,GRAPHITE,(680,y,120),(14,w,235),1)
# North wall leaves the 2.4m doorway fully open.
walls=root.child('NorthPressureLiner')
for x in [-412,412]:
    box(walls,WHITE,(x,578,350),(520,10,220),1.4)
    box(walls,GRAPHITE,(x,578,115),(520,12,220),1)
box(walls,GRAPHITE,(0,575,386),(242,22,236),2)
box(walls,WHITE,(0,555,350),(216,10,78),1.5)
box(walls,ALU,(0,548,300),(215,2,4),0.4)

# Four load-bearing transverse frames; paired shoulders support ceiling cassette rails.
for y in [-560,-190,200,560]:
    ribs=root.child('StructuralFrame_'+str(y).replace('-','N'))
    for x in [-657,657]:
        box(ribs,GUNMETAL,(x,y,236),(25,24,464),2)
        box(ribs,ALU,(x+(4 if x<0 else -4),y-13,238),(12,3,420),0.6)
    box(ribs,GUNMETAL,(0,y,470),(1290,26,30),2)
    box(ribs,ALU,(0,y-15,466),(1235,3,9),0.6)

ceiling=root.child('CeilingServiceCassettes')
for x in [-500,0,500]:
    for y,ln in [(-390,300),(5,380),(390,300)]:
        box(ceiling,GRAPHITE,(x,y,501),(300,ln,12),1.5)
        # removable acoustic/service inset, framed by the structural flanges
        box(ceiling,WHITE,(x,y,496.5),(276,ln-25,7),1)
for x in [-305,305]:
    box(ceiling,GUNMETAL,(x,0,474),(18,1110,16),1)

services=root.child('CoolingDistribution')
# A twin supply/return pipe run and a perforated ladder tray over the plant side.
for x,z,r in [(535,442,9),(575,442,7)]:
    services.add(tube(ALU,(x,0,z),r,r-1,1160,'y',20,0.5))
    for y in [-465,-105,280,500]:
        services.add(tube(GRAPHITE,(x,y,z),r+2,r,5,'y',20,0.3))
services=root.child('CableDistribution')
for x in [-545,-475]:box(services,GUNMETAL,(x,0,440),(8,1160,12),0.6)
for y in range(-555,556,35):box(services,GUNMETAL,(-510,y,434),(70,7,5),0.5)
for x in [-530,-514,-498]:services.add(cyl(RUBBER,(x,0,446),3,1160,'y',12,0.3))
for y in [-465,-105,280,500]:
    box(services,ALU,(555,y,467),(100,5,5),0.5)
    box(services,GUNMETAL,(-510,y,465),(100,8,6),0.5)
    for x in [-550,-470,525,590]:box(services,ALU,(x,y,476),(4,4,32),0.3)
task_support=root.child('ConsoleTaskLightSupports')
for x in [-292,-208]:task_support.add(cyl(ALU,(x,-190,390),0.6,130,'z',12,0.1))

floor=root.child('FloorDeckAndMaintenanceZones')
# A dark central route, wider offset deck plates, and removable perimeter service hatches.
for column,(x0,x1) in enumerate([(-675,-345),(-344,-55),(-54,345),(346,675)]):
    x,w=(x0+x1)/2,x1-x0
    for k,(y0,y1) in enumerate([(-590,-330),(-329,-10),(-9,340),(341,590)]):
        y,ln=(y0+y1)/2,y1-y0
        mat=GRAPHITE if column in [1,2] else GUNMETAL
        box(floor,mat,(x,y,1.0),(w,ln,2),0.4)
        # Flush fasteners distinguish removable deck panels without bright edge outlines.
        for dx,dy in [(-w/2+10,-ln/2+10),(w/2-10,ln/2-10)]:
            floor.add(cyl(ALU,(x+dx,y+dy,2.1),0.8,0.25,'z',8,0.05))
for x in [-95,95]:box(floor,ALU,(x,220,2.1),(1.3,660,0.2),0.02)
# Battery and thermal service clearance borders, interrupted at the operator approach.
for x,w in [(0,270),(490,270)]:
    for dx in [-w/2,w/2]:box(floor,HAZARD,(x+dx,-438,2.2),(2,215,0.2),0.02)
    box(floor,HAZARD,(x,-330,2.2),(w,2,0.2),0.02)
# Cable-access panels have recessed handles and a distinct finish.
for y in [-410,-80,280,500]:
    box(floor,ALU,(-610,y,2),(92,150,2),0.4)
    box(floor,GRAPHITE,(-610,y+48,3.1),(28,4,0.3),0.05)

# Permanent plant equipment replaces the nonvisual gameplay volumes, never their semantics.
plant=Node('OD_ENG_ServicePlant')
battery=plant.child('StationBatteryCabinet')
box(battery,GUNMETAL,(0,-500,98),(235,110,190),3)
box(battery,GRAPHITE,(0,-439,98),(215,10,174),1.5)
for x in [-73,0,73]:
    for z in [40,91,142]:
        box(battery,GRAPHITE,(x,-431,z),(64,12,43),1.2)
        box(battery,ALU,(x,-423,z+13),(48,2,4),0.4)
        box(battery,ION,(x-23,-422,z-9),(4,1,2),0.2)
box(battery,WHITE,(0,-433,194),(228,16,15),1)
thermal=plant.child('ThermalPlant')
box(thermal,GRAPHITE,(500,-480,10),(235,155,18),2)
for x in [445,555]:
    thermal.add(cyl(ALU,(x,-485,126),35,215,'z',32,3))
    for z in [35,90,175,220]:thermal.add(tube(GRAPHITE,(x,-485,z),37,35,7,'z',24,0.5))
    thermal.add(cyl(GUNMETAL,(x,-485,247),14,32,'z',20,1))
    thermal.add(cyl(ALU,(x,-420,250),9,130,'y',20,0.5))
    box(thermal,WHITE,(x,-446,120),(45,4,85),1)
box(thermal,GUNMETAL,(500,-355,251),(165,25,30),1.5)
for x,overhead_x in [(445,535),(555,575)]:
    thermal.add(cyl(ALU,(x,-355,345),8,190,'z',20,0.5))
    thermal.add(cyl(ALU,((x+overhead_x)/2,-355,442),8,overhead_x-x,'x',20,0.5))
    thermal.add(tube(GRAPHITE,(x,-355,285),10,8,5,'z',20,0.3))
air=plant.child('AirHandlingHousing')
box(air,GUNMETAL,(613,0,119),(96,230,232),2)
box(air,WHITE,(558,0,120),(12,214,220),1.5)
for y in [-68,0,68]:
    box(air,GRAPHITE,(549,y,126),(5,51,170),0.7)
    for z in range(57,201,12):box(air,ALU,(544,y,z),(6,46,3),0.3)
water=plant.child('WaterRecovery')
box(water,GUNMETAL,(616,347,12),(90,155,22),1)
for y in [310,385]:
    water.add(cyl(GRAPHITE,(613,y,109),26,174,'z',24,2))
    water.add(tube(ALU,(613,y,158),28,26,12,'z',24,0.5))
    water.add(cyl(ALU,(613,y,204),5,20,'z',16,0.4))
    water.add(cyl(ALU,(586.5,y,210),5,53,'x',16,0.5))
    water.add(cyl(ALU,(560,y,190),5,40,'z',16,0.4))
box(water,WHITE,(559,347,120),(12,140,110),1.5)
for y in [315,345,375]:box(water,GRAPHITE,(551,y,120),(3,20,80),0.4)
locker=plant.child('SparesLocker')
box(locker,GUNMETAL,(-638,295,110),(78,156,220),2)
for y in [257,333]:
    box(locker,WHITE,(-596,y,111),(7,73,205),1.2)
    box(locker,GRAPHITE,(-591,y-23,112),(3,5,35),0.5)
    box(locker,ALU,(-591,y+15,173),(1,30,8),0.3)
box(locker,GRAPHITE,(-638,295,6),(80,158,12),1)

reports={}
for n in [root,plant]:
    dest=OUT/(n.name+'.glb')
    write_glb(str(dest),n,{'odyssey_production':True,'units':'metres','authoring_origin_ue_cm':[2500,-800,0]})
    report,problems=validate_glb(str(dest))
    assert not problems,(n.name,problems)
    reports[n.name]=report
    print(n.name,report['triangles'],report['size_m'])
(OUT/'ArchitectureValidation.json').write_text(json.dumps(reports,indent=2))
