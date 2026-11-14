"""Removable liners, distribution manifold and inspection access; shared room origin in cm."""
from pathlib import Path
import sys,json
PROJECT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(PROJECT/'ArtSource/OdysseyAssetPack/Source'))
from od_core import Node,cbox,cyl,tube
from od_gltf import WHITE,GRAPHITE,GUNMETAL,ALU,RUBBER,write_glb,validate_glb
root=Node('OD_ENG_ServiceDetails')
def box(n,m,c,s,b=.3):n.add(cbox(m,c,s,bevel=min(b,min(s)*.2)))
# Separate bolted liner cassettes above the electrical wall. Flush removable covers.
for name,centres in [('ElectricalLiners_Port',[-510,-170]),('ElectricalLiners_Starboard',[170,510])]:
 n=root.child(name)
 for x in centres:
  for dx in [-78,78]:
   box(n,GUNMETAL,(x+dx,-568,349),(147,3,168),.6)
   box(n,WHITE,(x+dx,-565.5,349),(139,2,160),.5)
   for sx in [-62,62]:
    for z in [282,416]:n.add(cyl(ALU,(x+dx+sx,-563.8,z),1.1,.8,'y',12,.15))
   box(n,GRAPHITE,(x+dx,-563.5,288),(26,1,3),.2)
# Two isolated supply/return lines; an accessible manifold at mid-wall height.
n=root.child('WestCoolantManifold')
for z in [255,273]:
 n.add(cyl(ALU,(-658,-180,z),4,760,'y',16,.4))
 for y in [-500,-300,-100,100]:
  n.add(tube(GRAPHITE,(-658,y,z),5,4,4,'y',16,.2))
  box(n,GUNMETAL,(-667,y,z),(18,4,15),.3)
box(n,GRAPHITE,(-662,-240,169),(18,150,140),1)
box(n,WHITE,(-650,-240,169),(4,142,132),.7)
for y in [-280,-240,-200]:
 n.add(cyl(GUNMETAL,(-646,y,189),10,5,'x',20,.4))
 n.add(cyl(ALU,(-642,y,189),7,1,'x',20,.2))
 box(n,GRAPHITE,(-646,y,153),(2,20,9),.2)
 n.add(cyl(ALU,(-648,y,239),3,32,'z',16,.2))
# Inspection panels use graphite gaskets, recessed handles and fasteners.
for name,x,y,axis in [('SouthInspectionAccess',460,-565,'y'),('WestInspectionAccess',-660,70,'x')]:
 n=root.child(name)
 if axis=='y':
  box(n,GUNMETAL,(x,y,115),(170,7,170),1)
  box(n,GRAPHITE,(x,y+4,115),(160,2,160),.6)
  box(n,WHITE,(x,y+6,115),(150,2,150),.6)
  for dx in [-62,62]:box(n,GRAPHITE,(x+dx,y+8,115),(5,2,24),.3)
  for dx in [-67,67]:
   for z in [48,182]:n.add(cyl(ALU,(x+dx,y+8,z),1.2,1,'y',12,.1))
 else:
  box(n,GUNMETAL,(x,y,115),(7,150,170),1)
  box(n,WHITE,(x+5,y,115),(2,138,158),.6)
  for dy in [-56,56]:box(n,GRAPHITE,(x+7,y+dy,115),(2,5,24),.3)
  for dy in [-61,61]:
   for z in [48,182]:n.add(cyl(ALU,(x+7,y+dy,z),1.2,1,'x',12,.1))
n=root.child('NorthDoorServiceHeader')
box(n,GUNMETAL,(0,546,347),(188,7,57),1)
box(n,GRAPHITE,(0,541,347),(180,3,49),.7)
for x in [-83,83]:
 for z in [328,366]:n.add(cyl(ALU,(x,539,z),1.3,1,'y',12,.1))
out=PROJECT/'ArtSource/OdysseyProduction/OD_ENG_ServiceDetails.glb'
write_glb(str(out),root,{'odyssey_production':True,'units':'metres','authoring_origin_ue_cm':[2500,-800,0]})
report,problems=validate_glb(str(out));assert not problems,problems
out.with_suffix('.validation.json').write_text(json.dumps(report,indent=2));print('SERVICE_DETAILS_VALIDATED',report['triangles'])
