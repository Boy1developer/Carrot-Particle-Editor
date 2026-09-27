import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";
const eff = JSON.parse(readFileSync(new URL("../sample_effect.json", import.meta.url), "utf8"));
const e = new ParticleEngine();
e.loadEffect(eff);
for (let i = 0; i < 120; i++) e.update(1 / 60, 400, 300);
console.log("active after 2s:", e.activeCount);
if (!(e.activeCount > 0)) { console.error("FAIL: no particles spawned"); process.exit(1); }
// burst mode
const burst = JSON.parse(JSON.stringify(eff));
burst.emitter.mode = "Burst";
burst.emitter.reservoir = 100;
const e2 = new ParticleEngine();
e2.loadEffect(burst);
e2.update(1 / 60, 400, 300);
console.log("burst spawned:", e2.activeCount);
if (e2.activeCount !== 100) { console.error("FAIL: burst count"); process.exit(1); }
console.log("ENGINE OK");
