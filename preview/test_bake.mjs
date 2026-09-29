import * as THREE from "three";
import { bakeSkinnedMeshes } from "./three_scene.js";

// Synthetic 2-bone rig: bone1 moved AFTER bind, so the bake must apply
// (boneWorld * inverse) per vertex — the exact robot-preview case.
const geo = new THREE.BufferGeometry();
geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
  1, 0, 0,  // v0: bone0 only -> unchanged
  0, 0, 0,  // v1: bone1 only -> follows bone1's post-bind shift
  1, 0, 0,  // v2: 50/50 -> midpoint of both transforms
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
const sk = new THREE.SkinnedMesh(geo,
  new THREE.MeshStandardMaterial({ color: 0xff0000 }));
const bone0 = new THREE.Bone();
const bone1 = new THREE.Bone();
bone1.position.set(0, 2, 0);
root.add(sk);
sk.add(bone0);
bone0.add(bone1);
root.updateMatrixWorld(true);
sk.bind(new THREE.Skeleton([bone0, bone1]));
// post-bind rest shift (what a rigged GLB looks like at load)
bone1.position.set(0, 3, 0);

// an untouched plain mesh must survive the pass
const plain = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1),
  new THREE.MeshBasicMaterial());
plain.name = "plain";
root.add(plain);

const n = bakeSkinnedMeshes(root);
if (n !== 1) { console.error("FAIL: replaced", n); process.exit(1); }

let skinnedLeft = 0, baked = null, plainOk = false;
root.traverse((o) => {
  if (o.isSkinnedMesh) skinnedLeft++;
  if (o.isMesh && !o.isSkinnedMesh && o.geometry.getAttribute("position").count === 3) baked = o;
  if (o.name === "plain") plainOk = o.isMesh && !o.isSkinnedMesh;
});
if (skinnedLeft) { console.error("FAIL: skinned left"); process.exit(1); }
if (!baked) { console.error("FAIL: no baked mesh"); process.exit(1); }
if (!plainOk) { console.error("FAIL: plain mesh touched"); process.exit(1); }
if (baked.material.color.getHex() !== 0xff0000) {
  console.error("FAIL: material lost"); process.exit(1);
}
const p = baked.geometry.getAttribute("position");
const near = (i, x, y, z) =>
  Math.abs(p.getX(i) - x) < 1e-6 && Math.abs(p.getY(i) - y) < 1e-6 &&
  Math.abs(p.getZ(i) - z) < 1e-6;
if (!near(0, 1, 0, 0) || !near(1, 0, 1, 0) || !near(2, 1, 0.5, 0)) {
  console.error("FAIL: positions", [0, 1, 2].map((i) =>
    [p.getX(i), p.getY(i), p.getZ(i)]));
  process.exit(1);
}
const nr = baked.geometry.getAttribute("normal");
for (let i = 0; i < 3; i++) {
  if (Math.abs(nr.getX(i)) > 1e-6 || Math.abs(nr.getY(i) - 1) > 1e-6 ||
      Math.abs(nr.getZ(i)) > 1e-6) {
    console.error("FAIL: normal", i); process.exit(1);
  }
}
// second pass is a no-op
if (bakeSkinnedMeshes(root) !== 0) {
  console.error("FAIL: not idempotent"); process.exit(1);
}
console.log("BAKE OK");
