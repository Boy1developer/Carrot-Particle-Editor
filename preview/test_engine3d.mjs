import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";

const base = JSON.parse(readFileSync(new URL("../sample_effect.json", import.meta.url), "utf8"));

// 2D regression (morph engine)
const e = new ParticleEngine();
e.loadEffect(base);
for (let i = 0; i < 120; i++) e.update(1 / 60, 400, 300);
console.log("2d active after 2s:", e.activeCount);
if (!(e.activeCount > 0)) { console.error("FAIL: 2d no spawn"); process.exit(1); }

// 3D mode: type flag, 3D spawn, projection, morph sampling
const eff3d = JSON.parse(JSON.stringify(base));
eff3d.type = "3d";
eff3d.emitter.gravity = { x: 0, y: -100, z: 0 };
eff3d.emitter.emissionZone = { shape: "sphere", radius: 20, mode: "Surface" };
eff3d.emitter.propagationCone = { directionZ: 0, directionY: 0, spread: 60 };
eff3d.states = [
  { id: "s0", role: "birth", label: "b", duration: 0.5, shape: "cube", easing: "linear",
    appearance: { size: 10, sizeMax: 10, color: "#ffaa00", opacity: 255 },
    movement: { minSpeed: 80, maxSpeed: 80 } },
  { id: "s1", role: "death", label: "d", duration: 0.5, shape: "sphere", easing: "linear",
    appearance: { size: 4, sizeMax: 4, color: "#ff3300", opacity: 0 },
    movement: { minSpeed: 20, maxSpeed: 20 } },
];
const e3 = new ParticleEngine();
e3.loadEffect(eff3d);
if (!e3.is3D) { console.error("FAIL: is3D flag"); process.exit(1); }
for (let i = 0; i < 60; i++) e3.update(1 / 60, 0, 0);
console.log("3d active after 1s:", e3.activeCount);
if (!(e3.activeCount > 0)) { console.error("FAIL: 3d no spawn"); process.exit(1); }

// morph midpoint: size halfway 10->4; shape flips exactly mid-segment
const mid = e3.sampleAt(0.25, 0);
if (Math.abs(mid.size / 0.5 - 7) > 0.6) { console.error("FAIL: morph size", mid); process.exit(1); }
if (mid.shape !== "sphere") { console.error("FAIL: morph shape at mid should be death", mid); process.exit(1); }
const pre = e3.sampleAt(0.1, 0);
if (pre.shape !== "cube") { console.error("FAIL: morph shape pre-mid should be birth", pre); process.exit(1); }
console.log("3d morph midpoint: OK", JSON.stringify({ size: mid.size.toFixed(2), shape: mid.shape }));

// projection sanity: origin -> center, scale>0, moves with yaw
const [sx, sy, sc] = e3.project(0, 0, 0, 400, 300, 500);
if (sx !== 400 || sy !== 300 || sc <= 0) { console.error("FAIL: project origin", [sx, sy, sc]); process.exit(1); }
const yaw0 = e3.cam.yaw;
e3.cam.yaw += 0.5;
const [sx2] = e3.project(50, 0, 0, 400, 300, 500);
e3.cam.yaw = yaw0;
const [sx3] = e3.project(50, 0, 0, 400, 300, 500);
if (sx2 === sx3) { console.error("FAIL: yaw has no effect"); process.exit(1); }
console.log("3d projection+orbit: OK");
console.log("ENGINE3D OK");
