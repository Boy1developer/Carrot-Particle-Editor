import * as THREE from "three";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// Headless GDevelop-runtime harness for AvancedParticleEmitter3D.
// Executes the SHIPPED extension code (doStepPostEvents, extracted from
// AdvancedParticleEmitter.json) against stubbed gdjs objects + REAL three.js
// scene graph — no WebGL context needed (nothing renders, only scene-graph
// math + material state run). Catches init/load-time and per-frame crashes
// that syntax checks and pure-function tests cannot see.
const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(readFileSync(join(here, "..", "AdvancedParticleEmitter.json"), "utf8"));

function stepChunk() {
  const obj = doc.eventsBasedObjects.find((o) => o.name === "AvancedParticleEmitter3D");
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
  const big = out.find((c) => c.includes("MAIN UPDATE"));
  if (!big) throw new Error("runtime chunk not found");
  return big;
}

// Effect mirroring a real user export: 3D, pyramid->sphere morph,
// line zone, narrow cone, gravity, v1.1 keys, seed 0, fields off.
function userLikeEffect() {
  return {
    version: "1.1", type: "3d",
    emitter: {
      flow: 50, flowMode: "rate", flowInterval: 1, maxParticles: 400,
      reservoir: 50, mode: "Infinite", reverse: false, alignDir: false,
      billboard: true, rotationMode: "speed",
      gravity: { x: 20, y: -60, z: 0 },
      emissionZone: {
        shape: "line", radius: 10, width: 100, height: 60, depth: 60,
        length: 800, mode: "Surface", rotationX: 0, rotationY: 0,
        rotationZ: 0, showZone: true,
      },
      propagationCone: {
        directionX: 0, directionY: -90, directionZ: 0, spread: 15,
        showCone: true,
      },
      blendingMode: "Normal", seed: 0,
      fields: {
        turbulence: { amount: 0, scale: 0.05, speed: 1 },
        vortex: { strength: 0 },
        attractor: { x: 0, y: 0, z: 0, strength: 0, radius: 200 },
        collision: { planeY: null, bounce: 0.5, friction: 0.1 },
      },
    },
    states: [
      {
        id: "state_0", role: "birth", label: "birth", duration: 0.5,
        shape: "pyramid", easing: "linear", starPoints: 5, starInnerRatio: 0.4,
        appearance: { size: 8, sizeMax: 12, color: "#00f9ff", opacity: 255 },
        movement: {
          minSpeed: 60, maxSpeed: 160, minRotX: 0, maxRotX: 0,
          minRotY: 0, maxRotY: 0, minRotZ: -90, maxRotZ: 90,
        },
        customShapeRefs: [],
      },
      {
        id: "state_1", role: "death", label: "death", duration: 0.5,
        shape: "sphere", easing: "ease-out", starPoints: 5, starInnerRatio: 0.4,
        appearance: { size: 2, sizeMax: 4, color: "#ff3300", opacity: 0 },
        movement: {
          minSpeed: 20, maxSpeed: 60, minRotX: 0, maxRotX: 0,
          minRotY: 0, maxRotY: 0, minRotZ: -90, maxRotZ: 90,
        },
        customShapeRefs: [],
      },
    ],
  };
}

function makeWorld(effect, props = {}, runtime = true) {
  const threeScene = new THREE.Scene();
  const threeGroup = new THREE.Group();
  threeScene.add(threeGroup);
  const layerRenderer = {
    getThreeScene: () => threeScene,
    getThreeCamera: () => null,
    _threeScene: threeScene,
    _threeCamera: null,
  };
  const jsons = { "fx.json": effect };
  const P = {
    ParticleJSON: "fx.json",
    BlendingMode: "JSON",
    EmissionMode: "Infinite",
    CastShadow: false, ReceiveShadow: false, RenderEnabled: true,
    PreviewInEditor: false, ShowCone: false, ShowZone: false,
    SpeedMultiplier: 1, SizeMultiplier: 1, OpacityMultiplier: 1,
    OverrideGravity: false, GravityX: 0, GravityY: 0, GravityZ: 0,
    EmissionShape: "json", EmissionRadius: -1, EmissionSize2: -1,
    EmissionSize3: -1, MaxParticles: -1, Reservoir: -1, Reverse: "json",
    AlignDir: "json", Billboard: "json", RotationMode: "json",
    FlowMode: "json", FlowInterval: -1, Flow: -1,
    AtlasImage: "", ModelsGLB: "", GlbResource: "", ImageResource: "",
    DirectionY: -1, DirectionZ: -1, Spread: -1,
    ...props,
  };
  let elapsed = 0;
  const get = (k, fb) => (P[k] !== undefined && P[k] !== null ? P[k] : fb);
  const object = {
    id: 1,
    getRuntimeScene: () => gameScene,
    getLayer: () => "Base layer",
    getRenderer: () => ({ _threeGroup: threeGroup, getRendererObject: () => null }),
    getX: () => 0, getY: () => 0, getZ: () => 0,
    getRotationX: () => 0, getRotationY: () => 0,
    // GDevelop getElapsedTime() is a per-frame DELTA (not cumulative time)
    getElapsedTime: () => 16.7,
    _advance: (ms) => { elapsed += ms; },
    _getParticleJSON: () => get("ParticleJSON", ""),
    _getBlendingMode: () => get("BlendingMode", "JSON"),
    _getEmissionMode: () => get("EmissionMode", "json"),
    _getFlow: () => get("Flow", -1),
    _getFlowMode: () => get("FlowMode", "json"),
    _getFlowInterval: () => get("FlowInterval", -1),
    _getResetEffect: () => false,
    _setResetEffect: () => {},
    _getShowCone: () => get("ShowCone", false),
    _getShowZone: () => get("ShowZone", false),
    _getRenderEnabled: () => get("RenderEnabled", true),
    _getPreviewInEditor: () => get("PreviewInEditor", false),
    _getAtlasImage: () => get("AtlasImage", ""),
    _getModelsGLB: () => get("ModelsGLB", ""),
    _getGlbResource: () => get("GlbResource", ""),
    _getImageResource: () => get("ImageResource", ""),
    _getCastShadow: () => get("CastShadow", false),
    _getReceiveShadow: () => get("ReceiveShadow", false),
    _getDirectionY: () => get("DirectionY", -1),
    _getDirectionZ: () => get("DirectionZ", -1),
    _getSpread: () => get("Spread", -1),
    _setActiveParticles: () => {},
    _getDirection: () => "json",
    _getSpeedMultiplier: () => get("SpeedMultiplier", 1),
    _getSizeMultiplier: () => get("SizeMultiplier", 1),
    _getOpacityMultiplier: () => get("OpacityMultiplier", 1),
    _getEmissionShape: () => get("EmissionShape", "json"),
    _getEmissionRadius: () => get("EmissionRadius", -1),
    _getEmissionSize2: () => get("EmissionSize2", -1),
    _getEmissionSize3: () => get("EmissionSize3", -1),
    _getMaxParticles: () => get("MaxParticles", -1),
    _getReservoir: () => get("Reservoir", -1),
    _getReverse: () => get("Reverse", "json"),
    _getAlignDir: () => get("AlignDir", "json"),
    _getBillboard: () => get("Billboard", "json"),
    _getRotationMode: () => get("RotationMode", "json"),
    _getOverrideGravity: () => get("OverrideGravity", false),
    _getGravityX: () => get("GravityX", 0),
    _getGravityY: () => get("GravityY", 0),
    _getGravityZ: () => get("GravityZ", 0),
  };
  const gameScene = {
    getLayer: () => ({ getRenderer: () => layerRenderer }),
    getGame: () => ({
      getJsonManager: () => ({ getLoadedJson: (n) => jsons[n] || null }),
      // runtime === scene-is-current; editor omits getSceneStack entirely
      ...(runtime ? { getSceneStack: () => ({ getCurrentScene: () => gameScene }) } : {}),
    }),
  };
  return { object, gameScene, threeScene, layerRenderer };
}

const src = stepChunk();
const run = new Function("objects", "THREE", src);
// classic-mode THREE: InstancedMesh removed -> legacy mesh-per-particle path
const THREE_CLASSIC = { ...THREE };
delete THREE_CLASSIC.InstancedMesh;
delete THREE_CLASSIC.InstancedBufferAttribute;

const runClassic = new Function("objects", "THREE", src);

function drive(effect, frames, props, runtime = true, classic = false) {
  const { object } = makeWorld(effect, props, runtime);
  const runFn = classic ? runClassic : run;
  const threeNS = classic ? THREE_CLASSIC : THREE;
  for (let f = 0; f < frames; f++) {
    object._advance(16.7);
    runFn([object], threeNS);
  }
  return object;
}

// 1) user-like effect: init + 120 frames, particles alive, sane positions,
//    morph flip crossed (pyramid->sphere), no NaN.
let obj = drive(userLikeEffect(), 120);
let data = obj.__apfx3D;
if (!data) { console.error("FAIL: no runtime data after init"); process.exit(1); }
if (!(data.particles.length > 0)) { console.error("FAIL: no particles spawned"); process.exit(1); }
let bad = 0, shapes = new Set();
for (const p of data.particles) {
  if (!isFinite(p.x) || !isFinite(p.y) || !isFinite(p.z)) bad++;
  shapes.add(p.currentShape);
}
if (bad) { console.error("FAIL: NaN positions:", bad); process.exit(1); }
console.log("init+120f: OK particles=%d shapes=%s pool=%d",
  data.particles.length, [...shapes].join(","), data.pool.length);

// 2) seeded replay: same seed, fresh world, identical trajectories.
function snapshot(effect, frames) {
  const o = drive(effect, frames);
  return JSON.stringify(o.__apfx3D.particles.map((p) =>
    [p.x.toFixed(6), p.y.toFixed(6), p.z.toFixed(6)]));
}
const eff = userLikeEffect();
eff.emitter.seed = 4242;
const s1 = snapshot(eff, 90), s2 = snapshot(eff, 90);
if (s1 === "[]" || s1 !== s2) { console.error("FAIL: seeded replay"); process.exit(1); }
console.log("seeded replay: OK");

// 3) editor add-path (user scenario): no scene stack => _isEditor, preview
//    off => static preview mesh branch. Must not throw.
let ed = drive(userLikeEffect(), 30, { PreviewInEditor: false }, false);
let edata = ed.__apfx3D;
if (!edata) { console.error("FAIL: editor branch has no data"); process.exit(1); }
if (!edata._previewMesh) { console.error("FAIL: editor branch built no preview mesh"); process.exit(1); }
console.log("editor static preview: OK");

// 4) hostile matrix: guides, shadows, burst, align, camera billboard,
//    missing-model refs, overrides, reset mid-run. None may throw.
{
  const eff = userLikeEffect();
  eff.emitter.mode = "Burst";
  eff.emitter.reservoir = 60;
  eff.emitter.alignDir = true;
  eff.states[0].customShapeRefs = [];
  const { object, layerRenderer } = makeWorld(eff, {
    ShowCone: true, ShowZone: true, CastShadow: true,
    EmissionMode: "json", Flow: -1, MaxParticles: 500,
    EmissionShape: "json", AlignDir: "On",
  }, true);
  const cam = new THREE.PerspectiveCamera(60, 1, 1, 6000);
  cam.position.set(100, 100, 400);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld(true);
  layerRenderer.getThreeCamera = () => cam;
  layerRenderer._threeCamera = cam;
  for (let f = 0; f < 40; f++) {
    object._advance(16.7);
    if (f === 20) object._getResetEffect = () => true;
    if (f === 21) object._getResetEffect = () => false;
    run([object], THREE);
  }
  const d = object.__apfx3D;
  if (!d || !d.zoneGuide || !d.coneGuide) {
    console.error("FAIL: guides not built");
    process.exit(1);
  }
  console.log("hostile matrix: OK particles=%d pool=%d", d.particles.length, d.pool.length);
}

// 5) missing-model refs with empty ModelsGLB: warn path, no throw, fallback.
{
  const eff = userLikeEffect();
  eff.states[0].shape = "custom";
  eff.states[0].modelRefs = ["Nope"];
  eff.states[0].customShapeRefs = ["Nope"];
  const o = drive(eff, 40, {}, true);
  if (!o.__apfx3D) { console.error("FAIL: missing-model data"); process.exit(1); }
  console.log("missing-model fallback: OK particles=%d", o.__apfx3D.particles.length);
}

// 6) object renderer missing (getRenderer() null): objectGroup falls back
//    to null and the update uses object position. Must not throw.
{
  const eff = userLikeEffect();
  const { object } = makeWorld(eff, {}, true);
  object.getRenderer = () => null;
  for (let f = 0; f < 30; f++) {
    object._advance(16.7);
    run([object], THREE);
  }
  const d = object.__apfx3D;
  if (!d || d.objectGroup !== null || !(d.particles.length > 0)) {
    console.error("FAIL: null-renderer fallback");
    process.exit(1);
  }
  console.log("null-renderer fallback: OK particles=%d", d.particles.length);
}

// 7) instancing: buckets are created LAZILY (only shapes in use, not all
//    11), draw-call proxy collapses, all written matrices/colors finite.
{
  const eff = userLikeEffect();
  eff.emitter.seed = 4242;
  const o = drive(eff, 90, {}, true);
  const d = o.__apfx3D;
  if (!d._inst) { console.error("FAIL: no buckets"); process.exit(1); }
  const keys = Object.keys(d._inst);
  const allowed = new Set(["sphere", "cube", "diamond", "pyramid", "torus",
    "square", "triangle", "star", "line", "circle", "billboard"]);
  for (const k of keys) {
    if (!allowed.has(k)) { console.error("FAIL: bucket key", k); process.exit(1); }
  }
  if (!(keys.length >= 1 && keys.length <= 3)) {
    console.error("FAIL: lazy buckets", keys); process.exit(1);
  }
  let slots = 0;
  const groupChildren = d.particleGroup.children.length;
  for (const k of keys) {
    const bk = d._inst[k];
    if (bk.mesh.frustumCulled !== false) { console.error("FAIL: culling", k); process.exit(1); }
    if (bk.mesh.visible !== (bk.count > 0)) {
      console.error("FAIL: visibility", k, bk.count); process.exit(1);
    }
    slots += bk.count;
    const m = new THREE.Matrix4();
    for (let s = 0; s < bk.count; s++) {
      bk.mesh.getMatrixAt(s, m);
      for (const v of m.elements) {
        if (!isFinite(v)) { console.error("FAIL: matrix", k, s); process.exit(1); }
      }
      const c = new THREE.Color();
      bk.mesh.getColorAt(s, c);
      if (!isFinite(c.r + c.g + c.b)) { console.error("FAIL: color", k, s); process.exit(1); }
      const a = bk.alpha[s];
      if (!(a >= 0 && a <= 1)) { console.error("FAIL: alpha", k, s, a); process.exit(1); }
    }
  }
  const prims = d.particles.filter((p) => p.inst).length;
  if (slots !== prims || prims === 0) {
    console.error("FAIL: slots", slots, "prims", prims); process.exit(1);
  }
  if (groupChildren !== keys.length) {
    console.error("FAIL: draw calls", groupChildren, keys); process.exit(1);
  }
  console.log("instancing buckets: OK slots=%d buckets=%s", slots, keys.join(","));
}

// 8) classic fallback (no InstancedMesh in THREE): mesh-per-particle path,
//    still runs clean, every particle owns a mesh, no buckets.
{
  const eff = userLikeEffect();
  eff.emitter.seed = 4242;
  const o = drive(eff, 90, {}, true, true);
  const d = o.__apfx3D;
  if (d._inst !== undefined && d._inst !== null) {
    console.error("FAIL: buckets in classic mode"); process.exit(1);
  }
  if (!(d.particles.length > 0)) { console.error("FAIL: classic empty"); process.exit(1); }
  for (const p of d.particles) {
    if (!p.mesh) { console.error("FAIL: classic meshless"); process.exit(1); }
  }
  console.log("classic fallback: OK particles=%d", d.particles.length);
}

// 9) A/B appearance parity: same seeded effect, instanced vs classic must
//    draw identical per-shape multisets of [matrix, rgb, alpha] (tol 1e-3:
//    instanced storage is float32, classic float64 — real divergences are
//    orders of magnitude larger).
function collectAppearance(obj) {
  const d = obj.__apfx3D;
  const out = {};
  const push = (shape, m16, r, g, b, a) => {
    (out[shape] = out[shape] || []).push([...m16, r, g, b, a]);
  };
  if (d._inst) {
    const m = new THREE.Matrix4(), c = new THREE.Color();
    for (const k of Object.keys(d._inst)) {
      const bk = d._inst[k];
      for (let s = 0; s < bk.count; s++) {
        bk.mesh.getMatrixAt(s, m);
        bk.mesh.getColorAt(s, c);
        push(k, [...m.elements], c.r, c.g, c.b, bk.alpha[s]);
      }
    }
  } else {
    for (const p of d.particles) {
      p.mesh.updateMatrix();
      const mc = p.mesh.material.color;
      push(p.currentShape, [...p.mesh.matrix.elements], mc.r, mc.g, mc.b,
        p.mesh.material.opacity);
    }
  }
  for (const k of Object.keys(out)) {
    out[k].sort((x, y) => {
      for (let i = 0; i < x.length; i++) {
        if (Math.abs(x[i] - y[i]) > 1e-3) return x[i] - y[i];
      }
      return 0;
    });
  }
  return out;
}
{
  const eff = userLikeEffect();
  eff.emitter.seed = 4242;
  eff.emitter.blendingMode = "Normal";
  const a = collectAppearance(drive(eff, 90, {}, true, false));
  const b = collectAppearance(drive(eff, 90, {}, true, true));
  const ka = Object.keys(a).sort().join(","), kb = Object.keys(b).sort().join(",");
  if (ka !== kb) { console.error("FAIL: shape keys", ka, kb); process.exit(1); }
  for (const k of Object.keys(a)) {
    if (a[k].length !== b[k].length) {
      console.error("FAIL: count", k, a[k].length, b[k].length); process.exit(1);
    }
    for (let i = 0; i < a[k].length; i++) {
      for (let j = 0; j < a[k][i].length; j++) {
        if (Math.abs(a[k][i][j] - b[k][i][j]) > 1e-3) {
          console.error("FAIL: appearance", k, i, j, a[k][i][j], b[k][i][j]);
          process.exit(1);
        }
      }
    }
  }
  console.log("A/B parity: OK shapes=%s", ka);
}

// 10) diet exactness: F._dietOff must not change a single drawn value.
{
  const eff = userLikeEffect();
  eff.emitter.seed = 4242;
  const ref = collectAppearance(drive(eff, 90, {}, true, false));
  const eff2 = userLikeEffect();
  eff2.emitter.seed = 4242;
  const { object } = makeWorld(eff2, {}, true);
  for (let f = 0; f < 90; f++) {
    object._advance(16.7);
    run([object], THREE);
    if (f === 0) object.__apfx3DFns._dietOff = true;
  }
  const got = collectAppearance(object);
  const ka = Object.keys(ref).sort().join(","), kb = Object.keys(got).sort().join(",");
  if (ka !== kb) { console.error("FAIL: diet keys", ka, kb); process.exit(1); }
  for (const k of Object.keys(ref)) {
    if (ref[k].length !== got[k].length) {
      console.error("FAIL: diet count", k); process.exit(1);
    }
    for (let i = 0; i < ref[k].length; i++) {
      for (let j = 0; j < ref[k][i].length; j++) {
        if (ref[k][i][j] !== got[k][i][j]) {
          console.error("FAIL: diet value", k, i, j, ref[k][i][j], got[k][i][j]);
          process.exit(1);
        }
      }
    }
  }
  console.log("diet exactness: OK shapes=%s", ka);
}
console.log("EXT-RUNTIME-OK");
