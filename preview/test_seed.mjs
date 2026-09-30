import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// ---- preview engine determinism (seeded mulberry32) ----
function run(seed, steps = 120) {
  const eff = JSON.parse(
    readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "sample_effect.json"), "utf8"));
  eff.emitter.seed = seed;
  const e = new ParticleEngine();
  e.loadEffect(eff);
  for (let i = 0; i < steps; i++) e.update(1 / 60, 400, 300);
  const pts = [];
  for (let i = 0; i < e.activeCount; i++) {
    const st = e.particleState(i);
    pts.push([st.x.toFixed(6), st.y.toFixed(6)]);
  }
  return JSON.stringify(pts);
}
const a = run(4242), b = run(4242);
if (!a || a !== b) { console.error("FAIL: preview seed replay"); process.exit(1); }
if (run(4243) === a) { console.error("FAIL: seeds must diverge"); process.exit(1); }
if (!run(0)) { console.error("FAIL: seed 0"); process.exit(1); }
console.log("preview seed replay: OK");

// ---- extension RNG (extracted pure functions, stub-free) ----
const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(readFileSync(join(here, "..", "AdvancedParticleEmitter.json"), "utf8"));
function chunksOf(name) {
  const obj = doc.eventsBasedObjects.find((o) => o.name === name);
  const out = [];
  (function walk(evts) {
    for (const ev of evts || []) {
      if (ev.type === "BuiltinCommonInstructions::JsCode") {
        const code = ev.inlineCode || [];
        out.push(Array.isArray(code) ? code.join("\n") : String(code));
      }
      walk(ev.events);
    }
  })((obj.eventsFunctions || []).flatMap((f) => f.events || []));
  return out;
}
function extract(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) throw new Error("marker not found: " + marker);
  let j = src.indexOf("{", i);
  let depth = 0, k = j, quote = null;
  for (; k < src.length; k++) {
    const ch = src[k];
    if (quote) {
      if (ch === "\\") { k++; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === "'" || ch === '"') { quote = ch; continue; }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return src.slice(i, k + 1) + ";";
    }
  }
  throw new Error("unbalanced: " + marker);
}
for (const name of ["AvancedParticleEmitter2D", "AvancedParticleEmitter3D"]) {
  const t = chunksOf(name).join("\n");
  const F = {};
  new Function("F", extract(t, "F.srand = F.srand || function(seed) {"))(F);
  new Function("F", extract(t, "F.rrand = F.rrand || function() {"))(F);
  F.srand(777);
  const seq1 = [F.rrand(), F.rrand(), F.rrand(), F.rrand(), F.rrand()];
  F.srand(777);
  const seq2 = [F.rrand(), F.rrand(), F.rrand(), F.rrand(), F.rrand()];
  if (JSON.stringify(seq1) !== JSON.stringify(seq2)) {
    console.error("FAIL: extension RNG replay", name); process.exit(1);
  }
  if (!seq1.every((v) => v >= 0 && v < 1)) {
    console.error("FAIL: RNG range", name); process.exit(1);
  }
  F.srand(778);
  if (F.rrand() === seq1[0] && F.rrand() === seq1[1]) {
    console.error("FAIL: seeds must diverge", name); process.exit(1);
  }
  F.srand(0);
  const u = F.rrand();
  if (!(u >= 0 && u < 1)) { console.error("FAIL: unseeded fallback", name); process.exit(1); }
  if (t.split("Math.random()").length - 1 !== 1) {
    console.error("FAIL: expected only the F.rrand fallback", name); process.exit(1);
  }
  if (!t.includes("if (!st || !st.on) return Math.random();")) {
    console.error("FAIL: fallback shape changed", name); process.exit(1);
  }
  console.log("extension RNG: OK", name);
}
console.log("SEED-JS-OK");
