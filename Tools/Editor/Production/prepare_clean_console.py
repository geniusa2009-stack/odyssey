from pathlib import Path
import struct,json,copy
p=Path(__file__).resolve().parents[3]
b=(p/'ArtSource/OdysseyAssetPack/GLB/OD_ENG_PowerConsole.glb').read_bytes()
n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);size=struct.unpack_from('<I',b,20+n)[0];binary=b[28+n:28+n+size]
for node in d['nodes']:
 if node.get('name') in ['Screen_Main','Screen_Left','Screen_Right']:
  for prim in d['meshes'][node['mesh']]['primitives']:
   m=copy.deepcopy(d['materials'][prim['material']]);m['name']='OD_MAT_'+node['name'];prim['material']=len(d['materials']);d['materials'].append(m)
j=json.dumps(d,separators=(',',':')).encode();j+=b' '*(-len(j)%4);binary+=b'\0'*(-len(binary)%4)
out=p/'ArtSource/OdysseyProduction/OD_ENG_PowerConsole_Clean.glb'
out.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(j)+len(binary))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(binary),0x004e4942)+binary)
print('Clean console derivative prepared; geometry, UVs and pivots unchanged.')
