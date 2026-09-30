import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

// Unit-test the PURE blend-mapping functions shipped inside
// AdvancedParticleEmitter.json, using stubbed PIXI/THREE runtimes
// (mirrors the test_ext_bake.mjs extraction pattern).
const here = dirname(fileURLToPath(import.meta.url));
const doc = JSON.parse(
  readFileSync(join(here, "..", "AdvancedParticleEmitter.json"), "utf8"));

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

// Extract a brace-balanced function source starting at marker.
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

function eq(a, b, msg) {
  const x = JSON.stringify(a), y = JSON.stringify(b);
  if (x !== y) { console.error("FAIL:", msg, "got", x, "want", y); process.exit(1); }
}

const t2 = chunksOf("AvancedParticleEmitter2D").join("\n");
const t3 = chunksOf("AvancedParticleEmitter3D").join("\n");

// ---- 2D mapping (v7-like core: no SUBTRACT, no LIGHTEN) ----
const src2 = extract(t2, "var pixiBlendFor = function(mode, P) {");
const pixiBlendFor = new Function(src2 + "\nreturn pixiBlendFor;")();
const PIXI_FULL = { BLEND_MODES: { NORMAL: 0, ADD: 1, MULTIPLY: 2, SCREEN: 3, OVERLAY: 4, ERASE: 5 } };
const PIXI_BARE = { BLEND_MODES: { NORMAL: 0 } };
eq(pixiBlendFor("Additive", PIXI_FULL), { blend: 1, warn: null }, "2d additive");
eq(pixiBlendFor("Multiply", PIXI_FULL), { blend: 2, warn: null }, "2d multiply");
eq(pixiBlendFor("Subtractive", PIXI_FULL), { blend: 5, warn: null }, "2d subtract->erase");
eq(pixiBlendFor("Screen", PIXI_FULL), { blend: 3, warn: null }, "2d screen");
eq(pixiBlendFor("Overlay", PIXI_FULL), { blend: 4, warn: null }, "2d overlay");
eq(pixiBlendFor("Lighten", PIXI_FULL), { blend: 0, warn: "Lighten" }, "2d lighten fallback");
eq(pixiBlendFor("Normal", PIXI_FULL), { blend: 0, warn: null }, "2d normal");
eq(pixiBlendFor("Bogus", PIXI_FULL), { blend: 0, warn: null }, "2d bogus");
eq(pixiBlendFor("Screen", PIXI_BARE), { blend: 0, warn: "Screen" }, "2d screen missing");
eq(pixiBlendFor("Overlay", PIXI_BARE), { blend: 0, warn: "Overlay" }, "2d overlay missing");
eq(pixiBlendFor("Additive", PIXI_BARE), { blend: 0, warn: null }, "2d additive missing");
eq(pixiBlendFor("Additive", null), { blend: 0, warn: null }, "2d no pixi");
console.log("2D mapping: OK");

// ---- 3D mapping ----
const src3 = extract(t3, "F.threeBlendFor = F.threeBlendFor || function(mode, T) {");
const F3 = {};
new Function("F", "THREE", src3)(F3, undefined);
const threeBlendFor = F3.threeBlendFor;
const THREE_FULL = { NormalBlending: 0, AdditiveBlending: 1, SubtractiveBlending: 2, MultiplyBlending: 3, CustomBlending: 4, AddEquation: 5, OneFactor: 6, OneMinusSrcColorFactor: 7, MaxEquation: 8 };
const THREE_NO_MAX = { ...THREE_FULL };
delete THREE_NO_MAX.MaxEquation;
eq(threeBlendFor("Additive", THREE_FULL),
  { blending: 1, equation: null, src: null, dst: null, bake: "additive", warn: null }, "3d additive");
eq(threeBlendFor("Subtractive", THREE_FULL),
  { blending: 2, equation: null, src: null, dst: null, bake: "subtractive", warn: null }, "3d subtract");
eq(threeBlendFor("Multiply", THREE_FULL),
  { blending: 3, equation: null, src: null, dst: null, bake: "multiply", warn: null }, "3d multiply");
eq(threeBlendFor("Screen", THREE_FULL),
  { blending: 4, equation: 5, src: 6, dst: 7, bake: "additive", warn: null }, "3d screen");
eq(threeBlendFor("Lighten", THREE_FULL),
  { blending: 4, equation: 8, src: null, dst: null, bake: "lighten", warn: null }, "3d lighten");
eq(threeBlendFor("Overlay", THREE_FULL),
  { blending: 0, equation: null, src: null, dst: null, bake: "normal", warn: "Overlay" }, "3d overlay fallback");
eq(threeBlendFor("Lighten", THREE_NO_MAX),
  { blending: 0, equation: null, src: null, dst: null, bake: "normal", warn: "Lighten" }, "3d lighten no-max");
eq(threeBlendFor("Bogus", THREE_FULL),
  { blending: 0, equation: null, src: null, dst: null, bake: "normal", warn: null }, "3d bogus");
eq(threeBlendFor("Screen", null),
  { blending: 0, equation: null, src: null, dst: null, bake: "normal", warn: null }, "3d no three");
console.log("3D mapping: OK");

// ---- per-emitter resolution ----
const srcR = extract(t3, "F.resolveEmitterBlend = F.resolveEmitterBlend || function(objProp, emitterMode) {");
const FR = {};
new Function("F", srcR)(FR);
const resolve = FR.resolveEmitterBlend;
eq(resolve("JSON", "Screen"), "Screen", "json->emitter");
eq(resolve("", "Multiply"), "Multiply", "empty->emitter");
eq(resolve("Additive", "Screen"), "Additive", "explicit forces");
eq(resolve("JSON", ""), "Normal", "json+empty->normal");
eq(resolve(undefined, undefined), "Normal", "undef->normal");
console.log("resolution: OK");
console.log("BLEND-OK");
