import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";

const base = JSON.parse(readFileSync(new URL("../sample_effect.json", import.meta.url), "utf8"));
const e = new ParticleEngine();

// two-state morph: birth sphere -> death cube, 0.5s each
const eff = JSON.parse(JSON.stringify(base));
eff.type = "3d";
eff.states = [
  { id: "s0", role: "birth", label: "b", duration: 0.5, shape: "sphere",
    easing: "linear", appearance: { size: 8, color: "#ffffff", opacity: 255 },
    movement: { minSpeed: 0, maxSpeed: 0 }, modelRefs: ["coin"] },
  { id: "s1", role: "death", label: "d", duration: 0.5, shape: "cube",
    easing: "linear", appearance: { size: 8, color: "#ffffff", opacity: 255 },
    movement: { minSpeed: 0, maxSpeed: 0 }, modelRefs: ["box"] },
];
e.loadEffect(eff);

// outside the window -> null (pure shapes at both ends)
if (e.morphAt(0.0) !== null) { console.error("FAIL: t=0"); process.exit(1); }
if (e.morphAt(0.1) !== null) { console.error("FAIL: t=0.1"); process.exit(1); }
if (e.morphAt(0.49) !== null) { console.error("FAIL: t=0.49"); process.exit(1); }
// inside (0.25, 0.75) of the 0.5s birth segment -> companion + progress
const m1 = e.morphAt(0.2);
if (!m1 || m1.aShape !== "sphere" || m1.bShape !== "cube" ||
    m1.aRef !== "coin" || m1.bRef !== "box" || Math.abs(m1.t - 0.3) > 1e-9) {
  console.error("FAIL: mid-window", m1); process.exit(1);
}
const m2 = e.morphAt(0.3);
if (!m2 || Math.abs(m2.t - 0.7) > 1e-9) {
  console.error("FAIL: late-window", m2); process.exit(1);
}
// single state -> never morphs
const solo = JSON.parse(JSON.stringify(eff));
solo.states = [eff.states[0]];
e.loadEffect(solo);
if (e.morphAt(0.3) !== null) { console.error("FAIL: solo"); process.exit(1); }
console.log("MORPH OK");
