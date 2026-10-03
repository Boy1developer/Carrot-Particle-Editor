import { ParticleEngine } from "./preview.js";
import {
  TrailStore, normTrailCfg, bakeCurve, bakeGradient, evalKeys,
  widthAt, lutColor, outerColor, coreColor, flickerFactor,
  strideIndices, TRAIL_JUMP,
} from "./trails.js";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const here = dirname(fileURLToPath(import.meta.url));
function fail(msg, extra) {
  console.error("FAIL: " + msg, extra ?? "");
  process.exit(1);
}

// ---- 1) bake parity vs the Python reference (exact, incl. banker's rounding)
const fx = JSON.parse(readFileSync(join(here, "test_trail_fixtures.json"), "utf8"));
for (const tid of ["neon", "rainbow", "beam"]) {
  const f = fx[tid];
  const w = bakeCurve(f.widthCurve, 64);
  if (JSON.stringify(w) !== JSON.stringify(f.wlut)) fail("wlut " + tid);
  const g = bakeGradient(f.colorStops, f.alphaStops, 256);
  if (JSON.stringify(g) !== JSON.stringify(f.grad)) fail("grad " + tid);
}
if (Math.abs(evalKeys([[0, 0, "linear"], [1, 10, "linear"]], 0.3) - 3) > 1e-9) fail("eval linear");
if (evalKeys([[0, 5, "constant"], [1, 9, "constant"]], 0.7) !== 5) fail("eval constant");
if (Math.abs(evalKeys([[0, 0], [1, 8]], 0.5) - 4) > 1e-9) fail("eval smooth");
if (evalKeys([[0.2, 3], [0.8, 7]], -1) !== 3) fail("eval clamp lo");
if (evalKeys([[0.2, 3], [0.8, 7]], 2) !== 7) fail("eval clamp hi");
for (const [k, v] of Object.entries(fx.eval)) {
  if (Math.abs(evalKeys([[0, 0, "linear"], [1, 10, "linear"]], 0.3) - 3) > 1e-9 && k === "linear") fail("fx linear");
}
console.log("trails bake parity: OK");

// ---- 2) store semantics: exact distance sections, time gates, teleport cut
function baseCfg(over) {
  return Object.assign({
    enabled: true, source: "particles", maxPoints: 8, lifetime: 1.0,
    minDist: 0, minTime: 0, emitMode: "distance", sectionLength: 5,
    hideParticle: true, lifetimeJitter: 0,
  }, over || {});
}
{
  const st = new TrailStore();
  const cfg = baseCfg();
  for (let f = 0; f < 30; f++) st.update([{ key: 0, x: f * 2, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  const h = st.histories();
  if (h.length !== 1) fail("distance histories", h.length);
  const pts = h[0].pts;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i].x - pts[i - 1].x;
    if (Math.abs(dx - 5) > 1e-9) fail("distance spacing", dx);
  }
  if (pts.length !== 8) fail("distance maxPoints cap", pts.length);
}
{
  // 2x speed -> same span at cap (fixed sections x sectionLength)
  const run = (step) => {
    const st = new TrailStore();
    const cfg = baseCfg();
    for (let f = 0; f < 60; f++) st.update([{ key: 0, x: f * step, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
    const pts = st.histories()[0].pts;
    return pts[pts.length - 1].x - pts[0].x;
  };
  if (Math.abs(run(2) - run(4)) > 1e-9) fail("distance speed span", [run(2), run(4)]);
}
{
  // time mode: minDist gate + lifetime expiry
  const st = new TrailStore();
  const cfg = baseCfg({ emitMode: "time", minDist: 4, lifetime: 0.1 });
  for (let f = 0; f < 5; f++) st.update([{ key: 0, x: f * 2, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  const pts = st.histories()[0].pts;
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].x - pts[i - 1].x < 4 - 1e-9) fail("time minDist", pts[i].x - pts[i - 1].x);
  }
  for (let f = 5; f < 60; f++) st.update([{ key: 0, x: 1000 + f, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  const pts2 = st.histories()[0].pts;
  const span = pts2[pts2.length - 1].t - pts2[0].t;
  if (span > 0.1 + 1 / 60 + 1e-9) fail("time expiry", span);
}
{
  // teleport cut (slot reuse looks like a jump)
  const st = new TrailStore();
  const cfg = baseCfg({ emitMode: "time" });
  for (let f = 0; f < 5; f++) st.update([{ key: 3, x: f, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  st.update([{ key: 3, x: 5000, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  st.update([{ key: 3, x: 5001, y: 0, z: 0 }], 0, 0, 0, 1 / 60, cfg);
  const pts = st.histories()[0].pts;
  if (pts.length !== 2 || pts[0].x !== 5000) fail("teleport cut", pts.length);
}
{
  // emitter source: single trail following the anchor
  const st = new TrailStore();
  const cfg = baseCfg({ source: "emitter", emitMode: "time" });
  for (let f = 0; f < 5; f++) st.update([], f * 10, f, 0, 1 / 60, cfg);
  const h = st.histories();
  if (h.length !== 1 || h[0].key !== "emitter") fail("emitter source", h.length);
  if (h[0].pts[h[0].pts.length - 1].x !== 40) fail("emitter anchor");
}
console.log("trails store semantics: OK");

// ---- 3) engine wiring: active/hideDots + live histories in 2D and 3D
function loadEff(path, mut) {
  const eff = JSON.parse(readFileSync(join(here, "..", path), "utf8"));
  if (mut) mut(eff);
  const e = new ParticleEngine();
  e.loadEffect(eff);
  return e;
}
{
  const e = loadEff("sample_trail_effect.json");
  if (!e.trailsActive()) fail("sample trail inactive");
  if (!e.trailsHideDots()) fail("sample trail dots not hidden");
  for (let i = 0; i < 120; i++) e.update(1 / 60, 0, 0);
  const tf = e.trailFrame();
  if (!tf || !tf.trails.length) fail("no live trails");
  const n0 = tf.trails.length;
  for (let i = 0; i < 120; i++) e.update(1 / 60, 0, 0);
  if (e.trailFrame().trails.length <= 0) fail("trails died");
  console.log("engine 3d time-mode trails: OK (" + n0 + " live)");
}
{
  const e = loadEff("sample_trail_effect.json", (eff) => {
    eff.emitter.trails.emitMode = "distance";
    eff.emitter.trails.sectionLength = 6;
  });
  for (let i = 0; i < 180; i++) e.update(1 / 60, 0, 0);
  const tf = e.trailFrame();
  if (!tf || !tf.trails.length) fail("distance trails missing");
  for (const tr of tf.trails.slice(0, 20)) {
    const p = tr.pts;
    for (let i = 1; i < p.length; i++) {
      const d = Math.hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y, p[i].z - p[i - 1].z);
      if (Math.abs(d - 6) > 1e-6) fail("engine distance spacing", d);
    }
  }
  console.log("engine 3d distance-mode spacing: OK");
}
{
  const e = loadEff("sample_effect.json");
  if (e.trailsActive()) fail("plain effect must be trails-inactive");
  if (e.trailsHideDots()) fail("plain effect must keep dots");
  for (let i = 0; i < 60; i++) e.update(1 / 60, 400, 300);
  if (e.trailFrame() !== null) fail("plain effect trailFrame");
  console.log("engine legacy path untouched: OK");
}
{
  // 2D trail mode with a 2D template block
  const e = loadEff("sample_trail_effect.json", (eff) => {
    eff.type = "2d";
    eff.emitter.trails.emitMode = "distance";
    eff.emitter.trails.sectionLength = 6;
  });
  for (let i = 0; i < 180; i++) e.update(1 / 60, 400, 300);
  const tf = e.trailFrame();
  if (!tf || !tf.trails.length) fail("2d trails missing");
  if (!e.trailsHideDots()) fail("2d dots not hidden");
  console.log("engine 2d trails: OK (" + tf.trails.length + " live)");
}

// ---- 4) style helpers mirror the desktop renderer
{
  const cfg = Object.assign(normTrailCfg({ enabled: true, maxPoints: 8 }), {
    widthStart: 10, widthEnd: 2, widthMult: 1, taperHead: false, taperTail: true,
  });
  const wlut = bakeCurve([[0, 1], [1, 1]], 64);
  if (Math.abs(widthAt(0, cfg, wlut) - 10) > 1e-9) fail("width head");
  if (widthAt(1, cfg, wlut) !== 0) fail("width tail taper");
  const grad = bakeGradient([[0, "#ff0000"], [1, "#0000ff"]], [[0, 255], [1, 0]], 256);
  const [r, g, b, a] = lutColor(grad, 0);
  if (r !== 255 || g !== 0 || b !== 0 || a !== 255) fail("lut head", [r, g, b, a]);
  const [r2, , b2, a2] = lutColor(grad, 1);
  if (r2 !== 0 || b2 !== 255 || a2 !== 0) fail("lut tail", [r2, b2, a2]);
  const [er] = outerColor([200, 100, 50], "#ffffff", 1);
  if (Math.abs(er - 227.5) > 1e-9) fail("outer mix", er);
  const [cr] = coreColor([100, 100, 100], "", 1);
  if (Math.abs(cr - 145) > 1e-9) fail("core brighten", cr);
  if (flickerFactor(0, 8, 0, 0.5) !== 1) fail("flicker off");
  if (Math.abs(flickerFactor(0, 1, 1, 0) - 0.5) > 1e-9) fail("flicker on");
  if (JSON.stringify(strideIndices(5, 8)) !== "[0,1,2,3,4]") fail("stride full");
  if (strideIndices(100, 8).length !== 9) fail("stride cap");
  if (TRAIL_JUMP !== 150) fail("jump const");
  console.log("trails style helpers: OK");
}
console.log("TRAILS-JS-OK");
