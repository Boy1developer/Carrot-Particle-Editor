import { ParticleEngine } from "./preview.js";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

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
function close(a, b, tol, msg) {
  if (a.length !== b.length) { console.error("FAIL len:", msg); process.exit(1); }
  for (let i = 0; i < a.length; i++) {
    if (Math.abs(a[i] - b[i]) > tol) {
      console.error("FAIL:", msg, a, "want", b); process.exit(1);
    }
  }
}

// ---- pure helpers == Python reference values (tests/test_fields.py) ----
const F = {
  turbulence: { amount: 2.0, scale: 0.05, speed: 1.0 },
  vortex: { strength: 3.0 },
  attractor: { x: 1.0, y: 2.0, z: 3.0, strength: 4.0, radius: 200.0 },
  collision: { planeY: null, bounce: 0.5, friction: 0.1 },
};
for (const name of ["AvancedParticleEmitter2D", "AvancedParticleEmitter3D"]) {
  const t = chunksOf(name).join("\n");
  const G = {};
  new Function("F", extract(t, "F.fieldsActive = F.fieldsActive || function(Flds) {"))(G);
  new Function("F", extract(t, "F.fieldAccel = F.fieldAccel || function(x, y, z, age, Flds, ex, ey, ez, flat) {"))(G);
  new Function("F", extract(t, "F.fieldCollision = F.fieldCollision || function(Flds) {"))(G);
  if (G.fieldsActive({}) !== false || G.fieldsActive(null) !== false ||
      G.fieldsActive({ turbulence: { amount: 0 } }) !== false ||
      G.fieldsActive(F) !== true) {
    console.error("FAIL: gate", name); process.exit(1);
  }
  close(G.fieldAccel(10, 20, 30, 1.5, F, 0, 0, 0, false),
    [-2.538150573593, -2.663130821889, 0.264878016006], 1e-9, "accel3d " + name);
  close(G.fieldAccel(10, 20, 0, 1.5, F, 0, 0, 0, true),
    [-3.075640758651, 0.156763895690, 2.513097445525], 1e-9, "accel2d " + name);
  close(G.fieldAccel(10, 20, 30, 1.5, {}, 0, 0, 0, false), [0, 0, 0], 0, "accel off " + name);
  const col = G.fieldCollision({ collision: { planeY: 100, bounce: 0.5, friction: 0.1 } });
  if (!col || col.planeY !== 100 || col.bounce !== 0.5 || col.friction !== 0.1) {
    console.error("FAIL: collision", name, col); process.exit(1);
  }
  if (G.fieldCollision({}) !== null || G.fieldCollision({ collision: {} }) !== null) {
    console.error("FAIL: collision null", name); process.exit(1);
  }
  console.log("field helpers == Python: OK", name);
}

// ---- preview engine behavior ----
function run(fields, seed = 4242, steps = 120) {
  const eff = JSON.parse(readFileSync(join(here, "..", "sample_effect.json"), "utf8"));
  eff.emitter.seed = seed;
  if (fields !== undefined) eff.emitter.fields = fields;
  const e = new ParticleEngine();
  e.loadEffect(eff);
  for (let i = 0; i < steps; i++) e.update(1 / 60, 400, 300);
  const pts = [];
  for (let i = 0; i < e.activeCount; i++) {
    const st = e.particleState(i);
    pts.push([st.x, st.y, st.z]);
  }
  return JSON.stringify(pts);
}
const base = run(undefined);
if (base !== run({})) { console.error("FAIL: absent vs empty fields differ"); process.exit(1); }
const zero = {
  turbulence: { amount: 0, scale: 0.05, speed: 1 },
  vortex: { strength: 0 },
  attractor: { x: 0, y: 0, z: 0, strength: 0, radius: 200 },
  collision: { planeY: null, bounce: 0.5, friction: 0.1 },
};
if (base !== run(zero)) { console.error("FAIL: all-zero fields must be inert"); process.exit(1); }
console.log("fields-off identical: OK");
const turb = run({ turbulence: { amount: 60, scale: 0.05, speed: 2 } });
if (turb === base) { console.error("FAIL: turbulence inert"); process.exit(1); }
if (run({ turbulence: { amount: 60, scale: 0.05, speed: 2 } }) !== turb) {
  console.error("FAIL: turbulence replay"); process.exit(1);
}
console.log("turbulence deterministic: OK");
// collision plane invariant: nothing ends below the plane
const plane = run({ collision: { planeY: 290, bounce: 0.4, friction: 0.2 } });
if (plane === base) { console.error("FAIL: collision inert"); process.exit(1); }
for (const p of JSON.parse(plane)) {
  if (p[1] < 290 - 1e-9) { console.error("FAIL: penetration", p); process.exit(1); }
}
console.log("collision invariant: OK");
// attractor shrinks the cloud vs baseline
function meanR(s) {
  const pts = JSON.parse(s);
  return pts.reduce((a, p) => a + Math.hypot(p[0] - 400, p[1] - 300), 0) / Math.max(1, pts.length);
}
const attr = run({ attractor: { x: 400, y: 300, z: 0, strength: 400, radius: 2000 } });
if (!(meanR(attr) < meanR(base))) {
  console.error("FAIL: attractor", meanR(attr), meanR(base)); process.exit(1);
}
console.log("attractor pulls: OK");
console.log("FIELDS-JS-OK");
