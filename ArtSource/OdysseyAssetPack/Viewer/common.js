// ODYSSEY Asset Pack viewer - shared scene setup (three.js r160 from jsDelivr, pinned).
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export const ASSETS = [
  'OD_ENG_PowerConsole', 'OD_ENG_PowerBusB', 'OD_TRN_TrainingSimulator', 'OD_LAB_SampleAnalyzer',
  'OD_MCC_MainConsole', 'OD_ENV_SlidingDoor', 'OD_ENV_EmergencyBulkhead', 'OD_SYS_ORIONTerminal',
  'OD_SYS_ServerRack', 'OD_OBS_WindowFrame', 'OD_ENV_CeilingLight', 'OD_ENV_WallUtilityPanel',
  'OD_ENV_VentilationModule', 'OD_PROP_SupplyCrate', 'OD_MCC_MissionControlChair'];

// Unreal (x fwd, y right, z up) -> glTF/three (x, z, y)
export const ue2gl = (v) => new THREE.Vector3(v[0], v[2], v[1]);

export function makeRenderer(canvas, w, h) {
  const r = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  r.setPixelRatio(1);
  r.setSize(w, h, false);
  r.outputColorSpace = THREE.SRGBColorSpace;
  r.toneMapping = THREE.ACESFilmicToneMapping;
  r.toneMappingExposure = 1.0;
  r.shadowMap.enabled = true;
  r.shadowMap.type = THREE.PCFSoftShadowMap;
  return r;
}

export function makeStudio(renderer, bg = 0x8c8f92) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(bg);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(6, 10, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.bias = -0.0004;
  key.shadow.normalBias = 0.02;
  scene.add(key, key.target);
  const fill = new THREE.DirectionalLight(0xdfe8ff, 0.35);
  fill.position.set(-6, 4, -4);
  scene.add(fill);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.ShadowMaterial({ opacity: 0.22 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  return { scene, key, ground };
}

export function fitShadow(key, box) {
  const c = box.getCenter(new THREE.Vector3());
  const r = box.getSize(new THREE.Vector3()).length() * 0.75 + 0.5;
  key.target.position.copy(c);
  key.position.copy(c).add(new THREE.Vector3(6, 10, 5).normalize().multiplyScalar(r * 3));
  const cam = key.shadow.camera;
  cam.left = -r; cam.right = r; cam.top = r; cam.bottom = -r; cam.near = 0.1; cam.far = r * 8;
  cam.updateProjectionMatrix();
}

const loader = new GLTFLoader();
export function loadAsset(name) {
  return new Promise((res, rej) => loader.load(`../GLB/${name}.glb`, (g) => {
    g.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    res(g.scene);
  }, undefined, rej));
}

// 1.80 m human scale reference (viewer-only; never exported with any asset)
export function makeHuman(height = 1.8) {
  const g = new THREE.Group();
  g.name = 'HumanScaleReference_1p80m';
  const mat = new THREE.MeshStandardMaterial({ color: 0x3d6f8a, roughness: 0.7 });
  const s = height / 1.8;
  const part = (geo, x, y, z) => { const m = new THREE.Mesh(geo, mat); m.position.set(x * s, y * s, z * s); m.castShadow = true; g.add(m); return m; };
  part(new THREE.CapsuleGeometry(0.075 * s, 0.72 * s, 6, 12), 0, 0.44, 0.1);
  part(new THREE.CapsuleGeometry(0.075 * s, 0.72 * s, 6, 12), 0, 0.44, -0.1);
  part(new THREE.CapsuleGeometry(0.17 * s, 0.42 * s, 6, 16), 0, 1.2, 0);
  part(new THREE.CapsuleGeometry(0.05 * s, 0.55 * s, 6, 10), 0, 1.15, 0.24);
  part(new THREE.CapsuleGeometry(0.05 * s, 0.55 * s, 6, 10), 0, 1.15, -0.24);
  part(new THREE.SphereGeometry(0.105 * s, 20, 16), 0, 1.695, 0);
  const bar = new THREE.Mesh(new THREE.BoxGeometry(0.02, height, 0.02), new THREE.MeshBasicMaterial({ color: 0xffb000 }));
  bar.position.set(0, height / 2, 0.36 * s); g.add(bar);
  return g;
}

// ---------------------------------------------------------------- movable-part demo (od_motion extras)
export function collectMotions(root) {
  const out = [];
  root.traverse((o) => {
    const m = o.userData && o.userData.od_motion;
    if (m) out.push({ obj: o, m, p0: o.position.clone(), q0: o.quaternion.clone() });
  });
  return out;
}

export function applyMotions(list, t) {
  for (const it of list) {
    const { obj, m, p0, q0 } = it;
    obj.position.copy(p0); obj.quaternion.copy(q0);
    if (m.type === 'slide' || m.type === 'press') {
      const d = ue2gl(m.dir_ue).normalize();
      let cm = m.travel_cm ?? (m.range_cm ? m.range_cm[1] : 0);
      obj.position.addScaledVector(d, (cm / 100) * t);
    } else if (m.type === 'hinge' || m.type === 'rotate') {
      const axis = ue2gl(m.axis_ue).normalize();
      const deg = m.open_deg ?? (m.range_deg ? m.range_deg[1] : 0);
      let sign = 1;
      if (m.opens_toward_ue) {
        // choose the rotation sense that moves the part's centre toward the requested direction
        const want = ue2gl(m.opens_toward_ue);
        obj.updateWorldMatrix(true, true);
        const box = new THREE.Box3().setFromObject(obj);
        const c = box.getCenter(new THREE.Vector3());
        obj.updateWorldMatrix(true, false);
        const piv = new THREE.Vector3().setFromMatrixPosition(obj.matrixWorld);
        const rel = c.clone().sub(piv);
        const plus = rel.clone().applyAxisAngle(axis, THREE.MathUtils.degToRad(deg * 0.5));
        sign = plus.sub(rel).dot(want) >= 0 ? 1 : -1;
      }
      obj.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(deg * t * sign)));
    }
  }
}

export { THREE };
