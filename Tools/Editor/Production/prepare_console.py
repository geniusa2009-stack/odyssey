"""Decode embedded WebP to PNG using installed macOS ImageIO, preserving mesh BIN bytes."""
from pathlib import Path
import hashlib, json, struct, subprocess

PROJECT = Path(__file__).resolve().parents[3]
SOURCE = PROJECT / 'ArtSource/OdysseyProduction/SourceConsole/OD_ENG_PowerConsole_ScalePivotFixed.glb'
DEST = PROJECT / 'ArtSource/OdysseyProduction/OD_ENG_PowerConsole_PNG.glb'
scratch = PROJECT / 'Saved/Odyssey/ProductionWork/ConsoleTextures'
scratch.mkdir(parents=True, exist_ok=True)
b = SOURCE.read_bytes()
size, kind = struct.unpack_from('<II', b, 12)
assert kind == 0x4e4f534a
doc = json.loads(b[20:20+size])
bs, bk = struct.unpack_from('<II', b, 20+size)
assert bk == 0x004e4942
original_bin = b[28+size:28+size+bs]
binary = bytearray(original_bin)
original_meshes = json.dumps(doc['meshes'], sort_keys=True)
original_nodes = json.dumps(doc['nodes'], sort_keys=True)
for i, im in enumerate(doc['images']):
    view = doc['bufferViews'][im['bufferView']]
    start = view.get('byteOffset', 0)
    src = scratch / f'image_{i}.webp'
    dst = scratch / f'image_{i}.png'
    src.write_bytes(original_bin[start:start+view['byteLength']])
    subprocess.run(['/usr/bin/sips', '-s', 'format', 'png', str(src), '--out', str(dst)], check=True)
    data = dst.read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    binary.extend(b'\0' * (-len(binary) % 4))
    im['bufferView'] = len(doc['bufferViews'])
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data)})
    im['mimeType'] = 'image/png'
    binary.extend(data)
for tex in doc['textures']:
    ext = tex.get('extensions', {})
    if 'EXT_texture_webp' in ext:
        tex['source'] = ext.pop('EXT_texture_webp')['source']
    if not ext:
        tex.pop('extensions', None)
for key in ['extensionsRequired', 'extensionsUsed']:
    if key in doc:
        doc[key] = [x for x in doc[key] if x != 'EXT_texture_webp']
        if not doc[key]: doc.pop(key)
assert bytes(binary[:len(original_bin)]) == original_bin
assert json.dumps(doc['meshes'], sort_keys=True) == original_meshes
assert json.dumps(doc['nodes'], sort_keys=True) == original_nodes
doc['buffers'][0]['byteLength'] = len(binary)
j = json.dumps(doc, separators=(',', ':')).encode()
j += b' ' * (-len(j) % 4)
binary.extend(b'\0' * (-len(binary) % 4))
out = struct.pack('<4sII', b'glTF', 2, 28+len(j)+len(binary)) + struct.pack('<II', len(j), 0x4e4f534a) + j + struct.pack('<II', len(binary), 0x004e4942) + binary
DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_bytes(out)
print('Saved', DEST)
print('Geometry/nodes unchanged; original binary prefix preserved:', hashlib.sha256(original_bin).hexdigest())
