import * as THREE from "three";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// Extension trail support (shipped AdvancedParticleEmitter.json):
// pure F.trail* helpers extracted from the SHIPPED chunks + headless
// 3D (real three.js) and 2D (stub PIXI/gdjs) integration.
const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(readFileSync(join(here, "..", "AdvancedParticleEmitter.json"), "utf8"));
if (doc.version !== "0.1.3") {
  console.error("FAIL: extension version", doc.version);
  process.exit(1);
}
function fail(msg, extra) {
  console.error("FAIL: " + msg, extra ?? "");
  process.exit(1);
}
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
function trailBlock(name) {
  const c = chunksOf(name).find((x) => x.includes("// <carrot-trails-helpers>"));
  if (!c) fail("helpers missing in " + name);
  const a = "// <carrot-trails-helpers>", b = "// </carrot-trails-helpers>";
  return c.slice(c.indexOf(a), c.indexOf(b) + b.length) + ";";
}
const block2D = trailBlock("AvancedParticleEmitter2D");
const block3D = trailBlock("AvancedParticleEmitter3D");
if (block2D !== block3D) fail("2D/3D helper drift");
const F = {};
new Function("F", block2D)(F);

// ---- 1) bake parity vs the Python reference (exact)
const fx = JSON.parse(readFileSync(join(here, "test_trail_fixtures.json"), "utf8"));
for (const tid of ["neon", "rainbow", "beam"]) {
  const f = fx[tid];
  if (JSON.stringify(F.trailBakeCurve(f.widthCurve, 64)) !== JSON.stringify(f.wlut)) fail("wlut " + tid);
  if (JSON.stringify(F.trailBakeGrad(f.colorStops, f.alphaStops, 256)) !== JSON.stringify(f.grad)) fail("grad " + tid);
}
if (F.trailEvalKeys([[0, 0, "linear"], [1, 10, "linear"]], 0.3) !== 3) fail("eval linear");
if (F.trailEvalKeys([[0, 5, "constant"], [1, 9, "constant"]], 0.7) !== 5) fail("eval constant");
if (Math.abs(F.trailEvalKeys([[0, 0], [1, 8]], 0.5) - 4) > 1e-9) fail("eval smooth");
if (F.trailNorm(null) !== null || F.trailNorm({}) !== null) fail("norm off");
if (F.trailNorm({ enabled: true, maxPoints: 1 }) !== null) fail("norm maxPoints");
const tb0 = F.trailBuild({ enabled: true, maxPoints: 8 });
if (!tb0 || tb0.cfg.hideParticle !== true || tb0.wlut.length !== 64 || tb0.grad.length !== 256) fail("build");
console.log("ext trails helpers parity: OK");

// ---- 2) store semantics on the SHIPPED helpers
{
  const cfg = Object.assign(F.trailNorm({ enabled: true, maxPoints: 8 }),
    { emitMode: "distance", sectionLength: 5, minDist: 0, minTime: 0 });
  const st = F.trailStoreNew();
  const items = (f) => [{ k: 0, x: f * 2, y: 0, z: 0 }];
  for (let f = 0; f < 30; f++) {
    st.now += 1 / 60;
    for (const it of items(f)) F.trailPush(st, it.k, it.x, it.y, it.z, cfg);
  }
  const keys = Object.keys(st.hist);
  if (keys.length !== 1) fail("store keys", keys.length);
  const pts = st.hist[keys[0]];
  if (pts.length !== 8) fail("store cap", pts.length);
  for (let i = 1; i < pts.length; i++) {
    if (Math.abs((pts[i].x - pts[i - 1].x) - 5) > 1e-9) fail("store spacing");
  }
  F.trailSweep(st, 0, false);
  if (Object.keys(st.hist).length !== 0) fail("sweep");
}
console.log("ext trails store: OK");

// ---- 3) 3D integration: real three.js scene graph, no WebGL context
function trailEffect3D(hide) {
  const eff = JSON.parse(readFileSync(join(here, "..", "sample_trail_effect.json"), "utf8"));
  eff.emitter.trails.hideParticle = hide;
  return eff;
}
function makeWorld3D(effect) {
  const threeScene = new THREE.Scene();
  const threeGroup = new THREE.Group();
  threeScene.add(threeGroup);
  const cam = new THREE.PerspectiveCamera(60, 1, 1, 6000);
  cam.position.set(100, 100, 400);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld(true);
  const layerRenderer = {
    getThreeScene: () => threeScene,
    getThreeCamera: () => cam,
    _threeScene: threeScene,
    _threeCamera: cam,
  };
  const jsons = { "fx.json": effect };
  const P = {
    ParticleJSON: "fx.json", BlendingMode: "JSON", EmissionMode: "Infinite",
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
  };
  const get = (k, fb) => (P[k] !== undefined && P[k] !== null ? P[k] : fb);
  const object = {
    id: 7,
    getRuntimeScene: () => gameScene,
    getLayer: () => "Base layer",
    getRenderer: () => ({ _threeGroup: threeGroup, getRendererObject: () => null }),
    getX: () => 0, getY: () => 0, getZ: () => 0,
    getRotationX: () => 0, getRotationY: () => 0,
    getElapsedTime: () => 16.7,
    _advance: () => {},
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
      getSceneStack: () => ({ getCurrentScene: () => gameScene }),
    }),
  };
  return { object, threeScene };
}
{
  const src = chunksOf("AvancedParticleEmitter3D").find((c) => c.includes("MAIN UPDATE"));
  const run = new Function("objects", "THREE", src);
  const { object } = makeWorld3D(trailEffect3D(true));
  for (let f = 0; f < 120; f++) run([object], THREE);
  const d = object.__apfx3D;
  if (!d || !d.trailB || !d.trailB.cfg) fail("3d trailB missing");
  const keys = Object.keys(d.trailB.store.hist).filter((k) => d.trailB.store.hist[k].length >= 2);
  if (!keys.length) fail("3d no histories");
  if (!d.trailPool || d.trailPool.length !== 128) fail("3d pool", d.trailPool && d.trailPool.length);
  const vis = d.trailPool.filter((m) => m.visible).length;
  if (!vis) fail("3d no visible ribbons");
  let dots = 0;
  for (const k in (d._inst || {})) dots += d._inst[k].count || 0;
  if (dots !== 0) fail("3d dots not hidden", dots);
  let nan = 0;
  for (const m of d.trailPool) {
    if (!m.visible) continue;
    const a = m.geometry.getAttribute("position").array;
    for (let i = 0; i < a.length; i++) if (!isFinite(a[i])) nan++;
  }
  if (nan) fail("3d ribbon NaN", nan);
  console.log("ext 3d ribbons-only: OK trails=%d ribbons=%d", keys.length, vis);

  const hyb = makeWorld3D(trailEffect3D(false));
  for (let f = 0; f < 120; f++) run([hyb.object], THREE);
  const hd = hyb.object.__apfx3D;
  let hdots = 0;
  for (const k in (hd._inst || {})) hdots += hd._inst[k].count || 0;
  const hvis = hd.trailPool.filter((m) => m.visible).length;
  if (!hdots) fail("3d hybrid lost dots");
  if (!hvis) fail("3d hybrid lost ribbons");
  console.log("ext 3d hybrid: OK dots=%d ribbons=%d", hdots, hvis);
}

// ---- 4) 2D integration: stub PIXI + stub gdjs
function trailEffect2D(hide) {
  const eff = JSON.parse(readFileSync(join(here, "..", "sample_trail_effect.json"), "utf8"));
  eff.type = "2d";
  eff.emitter.trails.hideParticle = hide;
  return eff;
}
class StubC {
  constructor() {
    this.children = [];
    this.visible = true;
    this.parent = null;
    this.position = { x: 0, y: 0, set: (x, y) => { this.position.x = x; this.position.y = y; } };
    this.scale = { x: 1, y: 1, set: (x, y) => { this.scale.x = x; this.scale.y = y; } };
    this.rotation = 0; this.alpha = 1; this.tint = 0; this.blendMode = 0;
    this.anchor = { set: () => {} };
    this.userData = {};
  }
  addChild(c) { this.children.push(c); c.parent = this; return c; }
  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    c.parent = null;
    return c;
  }
  removeChildren() {
    for (const c of this.children) c.parent = null;
    this.children = [];
  }
  destroy() { this.parent = null; this.children = []; }
}
class StubG extends StubC {
  constructor() { super(); this.polys = 0; }
  clear() {}
  beginFill() {}
  drawCircle() {}
  drawRect() {}
  drawPolygon() { this.polys++; }
  endFill() {}
}
class StubS extends StubC {
  constructor() { super(); this.texture = null; }
  destroy() { this.parent = null; }
}
const PIXI = {
  Container: StubC, Graphics: StubG, Sprite: StubS, Texture: { EMPTY: {} },
};
function makeWorld2D(effect) {
  const pixiContainer = new StubC();
  const layerRenderer = {
    getRendererObject: () => pixiContainer,
    addRendererObject: (c) => pixiContainer.addChild(c),
  };
  const jsons = { "fx.json": effect };
  const P = {
    ParticleJSON: "fx.json", Direction: "json", Spread: "json",
    Flow: -1, FlowMode: "json", FlowInterval: -1, MaxParticles: -1,
    Reservoir: -1, Reverse: "json", AlignDir: "json", RotationMode: "json",
    OverrideGravity: false, GravityX: 0, GravityY: 0,
    EmissionShape: "json", EmissionRadius: -1, EmissionSize2: -1,
    EmissionMode: "json", ResetEffect: false, ShowCone: false,
    ShowZone: false, RenderEnabled: true, ImageResource: "",
    AtlasImage: "", BlendingMode: "JSON", SpeedMultiplier: 1,
    SizeMultiplier: 1, OpacityMultiplier: 1,
  };
  const get = (k, fb) => (P[k] !== undefined && P[k] !== null ? P[k] : fb);
  const object = {
    id: 9,
    getRuntimeScene: () => gameScene,
    getLayer: () => "Base layer",
    getRenderer: () => ({ getRendererObject: () => pixiContainer }),
    getZOrder: () => 0,
    getX: () => 400, getY: () => 300,
    getElapsedTime: () => 16.7,
    _setActiveParticles: () => {},
    _getParticleJSON: () => get("ParticleJSON", ""),
    _getDirection: () => get("Direction", "json"),
    _getSpread: () => get("Spread", "json"),
    _getFlow: () => get("Flow", -1),
    _getFlowMode: () => get("FlowMode", "json"),
    _getFlowInterval: () => get("FlowInterval", -1),
    _getMaxParticles: () => get("MaxParticles", -1),
    _getReservoir: () => get("Reservoir", -1),
    _getReverse: () => get("Reverse", "json"),
    _getAlignDir: () => get("AlignDir", "json"),
    _getRotationMode: () => get("RotationMode", "json"),
    _getOverrideGravity: () => get("OverrideGravity", false),
    _getGravityX: () => get("GravityX", 0),
    _getGravityY: () => get("GravityY", 0),
    _getEmissionShape: () => get("EmissionShape", "json"),
    _getEmissionRadius: () => get("EmissionRadius", -1),
    _getEmissionSize2: () => get("EmissionSize2", -1),
    _getEmissionMode: () => get("EmissionMode", "json"),
    _getResetEffect: () => get("ResetEffect", false),
    _getShowCone: () => get("ShowCone", false),
    _getShowZone: () => get("ShowZone", false),
    _getRenderEnabled: () => get("RenderEnabled", true),
    _getImageResource: () => get("ImageResource", ""),
    _getAtlasImage: () => get("AtlasImage", ""),
    _getBlendingMode: () => get("BlendingMode", "JSON"),
    _getSpeedMultiplier: () => get("SpeedMultiplier", 1),
    _getSizeMultiplier: () => get("SizeMultiplier", 1),
    _getOpacityMultiplier: () => get("OpacityMultiplier", 1),
  };
  const gameScene = {
    getLayer: () => ({ getRenderer: () => layerRenderer }),
    getGame: () => ({
      getJsonManager: () => ({ getLoadedJson: (n) => jsons[n] || null }),
      getImageManager: () => null,
      getSceneStack: () => ({ getCurrentScene: () => gameScene }),
    }),
  };
  return { object };
}
{
  const src = chunksOf("AvancedParticleEmitter2D").find((c) => c.includes("Update particles (swap-and-pop)"));
  if (!src) fail("2d main chunk not found");
  const run = new Function("objects", "PIXI", src);
  const { object } = makeWorld2D(trailEffect2D(true));
  for (let f = 0; f < 120; f++) run([object], PIXI);
  const d = object.__apfx2D;
  if (!d || !d.trailB || !d.trailB.cfg) fail("2d trailB missing");
  if (!d.trailGfx || d.trailGfx.polys <= 0) fail("2d no ribbon polys");
  const hidden = d.particles.filter((p) => p.displayObj.visible === false).length;
  if (hidden !== d.particles.length || !d.particles.length) fail("2d dots not hidden", [hidden, d.particles.length]);
  console.log("ext 2d ribbons-only: OK particles=%d polys=%d", d.particles.length, d.trailGfx.polys);

  const hyb = makeWorld2D(trailEffect2D(false));
  for (let f = 0; f < 120; f++) run([hyb.object], PIXI);
  const hd = hyb.object.__apfx2D;
  const shown = hd.particles.filter((p) => p.displayObj.visible !== false).length;
  if (shown !== hd.particles.length || !shown) fail("2d hybrid lost dots");
  if (!hd.trailGfx || hd.trailGfx.polys <= 0) fail("2d hybrid lost ribbons");
  console.log("ext 2d hybrid: OK dots=%d polys=%d", shown, hd.trailGfx.polys);

  const leg = makeWorld2D(JSON.parse(readFileSync(join(here, "..", "sample_effect.json"), "utf8")));
  for (let f = 0; f < 60; f++) run([leg.object], PIXI);
  const ld = leg.object.__apfx2D;
  if (!ld) fail("2d legacy no data");
  if (ld.trailB !== null && ld.trailB !== undefined) fail("2d legacy trailB set");
  if (ld.trailGfx) fail("2d legacy gfx created");
  console.log("ext 2d legacy untouched: OK particles=%d", ld.particles.length);
}
console.log("EXT-TRAILS-OK");
