import * as THREE from "three";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// Execute the EXACT function shipped inside AdvancedParticleEmitter.json.
// (Extracted at runtime so the test never depends on a temp scan artifact.)
const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(readFileSync(join(here, "..", "AdvancedParticleEmitter.json"), "utf8"));
const obj3d = doc.eventsBasedObjects.find((o) => o.name === "AvancedParticleEmitter3D");
const chunks = [];
(function walk(evts) {
  for (const ev of evts || []) {
    if (ev.type === "BuiltinCommonInstructions::JsCode") {
      const code = ev.inlineCode || [];
      chunks.push(Array.isArray(code) ? code.join("\n") : String(code));
    }
    walk(ev.events);
  }
})((obj3d.eventsFunctions || []).flatMap((f) => f.events || []));
const big = chunks.join("\n");
const m = big.match(/  function apfxBakeSkinned\(root\) \{[\s\S]*?\n  \}\n/);
if (!m) { console.error("FAIL: bake fn not found in extension"); process.exit(1); }
const src = m[0];
globalThis.THREE = THREE;
const fn = new Function(src + "\nreturn apfxBakeSkinned;")();
if (typeof fn !== "function") { console.error("FAIL: no fn"); process.exit(1); }

const geo = new THREE.BufferGeometry();
geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
  1, 0, 0, 0, 0, 0, 1, 0, 0,
]), 3));
geo.setAttribute("normal", new THREE.BufferAttribute(new Float32Array([
  0, 1, 0, 0, 1, 0, 0, 1, 0,
]), 3));
geo.setAttribute("skinIndex", new THREE.BufferAttribute(new Float32Array([
  0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0,
]), 4));
geo.setAttribute("skinWeight", new THREE.BufferAttribute(new Float32Array([
  1, 0, 0, 0, 1, 0, 0, 0, 0.5, 0.5, 0, 0,
]), 4));
const root = new THREE.Group();
const sk = new THREE.SkinnedMesh(geo, new THREE.MeshStandardMaterial());
const b0 = new THREE.Bone();
const b1 = new THREE.Bone();
b1.position.set(0, 2, 0);
root.add(sk);
sk.add(b0);
b0.add(b1);
root.updateMatrixWorld(true);
sk.bind(new THREE.Skeleton([b0, b1]));
b1.position.set(0, 3, 0);

if (fn(root) !== 1) { console.error("FAIL: count"); process.exit(1); }
let baked = null;
root.traverse((o) => {
  if (o.isSkinnedMesh) { console.error("FAIL: skinned left"); process.exit(1); }
  if (o.isMesh && o.geometry.getAttribute("position").count === 3) baked = o;
});
const p = baked.geometry.getAttribute("position");
const exp = [[1, 0, 0], [0, 1, 0], [1, 0.5, 0]];
for (let i = 0; i < 3; i++) {
  if (Math.abs(p.getX(i) - exp[i][0]) > 1e-6 ||
      Math.abs(p.getY(i) - exp[i][1]) > 1e-6 ||
      Math.abs(p.getZ(i) - exp[i][2]) > 1e-6) {
    console.error("FAIL: pos", i, p.getX(i), p.getY(i), p.getZ(i));
    process.exit(1);
  }
}
console.log("EXT-BAKE OK");
