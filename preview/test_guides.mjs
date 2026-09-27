import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";

const base = JSON.parse(readFileSync(new URL("../sample_effect.json", import.meta.url), "utf8"));
const e = new ParticleEngine();
const v0 = e.effectVersion;
e.loadEffect(base);
if (!(e.effectVersion > v0)) { console.error("FAIL: effectVersion not bumped"); process.exit(1); }
const z = e.zoneInfo();
if (z.shape !== "circle" || z.radius !== 50 || z.mode !== "surface") {
  console.error("FAIL: zoneInfo", z); process.exit(1);
}
const c = e.coneInfo();
if (c.direction !== 270 || c.spread !== 60) {
  console.error("FAIL: coneInfo", c); process.exit(1);
}
// 3D-style payload
const eff3d = JSON.parse(JSON.stringify(base));
eff3d.type = "3d";
eff3d.emitter.emissionZone = { shape: "box", width: 60, height: 10, depth: 20, mode: "Surface" };
eff3d.emitter.propagationCone = { directionZ: 45, directionY: 10, spread: 30 };
e.loadEffect(eff3d);
const z3 = e.zoneInfo();
if (z3.shape !== "box" || z3.width !== 60 || z3.depth !== 20) {
  console.error("FAIL: zoneInfo 3d", z3); process.exit(1);
}
const c3 = e.coneInfo();
if (c3.direction !== 45 || c3.directionY !== 10 || c3.spread !== 30) {
  console.error("FAIL: coneInfo 3d", c3); process.exit(1);
}
// mutating the copy must not affect the engine
z3.shape = "hacked";
if (e.zoneInfo().shape !== "box") { console.error("FAIL: zoneInfo not a copy"); process.exit(1); }
console.log("GUIDES_API OK");
