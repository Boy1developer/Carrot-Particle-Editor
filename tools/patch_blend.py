# Adds Screen / Lighten / Overlay blend modes to AdvancedParticleEmitter.json
# (Phase 6b). Run once; re-runs are a no-op.
#
# Audit basis (see PROGRESS.md Phase 6a): GDevelop Pixi is v7.2 (core modes:
# normal/add/multiply/screen/overlay/erase — NO subtract, NO lighten).
# Three.js does Screen via CustomBlending and Lighten via MaxEquation;
# Overlay has no fixed-function equivalent and falls back to Normal there.
# Mappings are pure functions so preview/test_blend.mjs can unit-test them
# headless with stubbed PIXI/THREE. Unsupported modes degrade to Normal with
# a single console.warn (never per frame, never throwing).
#
# Raw-JSON edits (choices, descriptions, comments, version) assert exact
# occurrence counts; chunk edits assert single occurrence. The modified
# chunks pass node --check.
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")

NEW_MODES = ["Screen", "Lighten", "Overlay"]
FULL_DESC = ("How particles blend with background: Normal, Additive, "
             "Subtractive, Multiply, Screen, Lighten, Overlay")
OLD_DESC = ("How particles blend with background: Normal, Additive, "
            "Subtractive, Multiply")


def _rep_once(text, old, new, what):
    assert text.count(old) == 1, "%s anchor x%d" % (what, text.count(old))
    return text.replace(old, new, 1)


def _ensure(raw, old, new, want, what):
    """Idempotent replacement: applies once, skips when already applied."""
    if new in raw:
        return raw
    assert raw.count(old) == want, "%s anchor x%d (want %d)" % (what, raw.count(old), want)
    return raw.replace(old, new)


def _rep_all(text, old, new, want, what):
    assert text.count(old) == want, "%s anchor x%d (want %d)" % (what, text.count(old), want)
    return text.replace(old, new)


PIXI_BLEND_FOR = """var pixiBlendFor = function(mode, P) {
  P = P || ((typeof PIXI !== "undefined") ? PIXI : null);
  var B = (P && P.BLEND_MODES) || {};
  var N = (B.NORMAL !== undefined && B.NORMAL !== null) ? B.NORMAL : 0;
  switch (mode) {
    case "Additive": return { blend: ((B.ADD !== undefined && B.ADD !== null) ? B.ADD : N), warn: null };
    case "Multiply": return { blend: ((B.MULTIPLY !== undefined && B.MULTIPLY !== null) ? B.MULTIPLY : N), warn: null };
    case "Subtractive": return { blend: ((B.SUBTRACT !== undefined && B.SUBTRACT !== null) ? B.SUBTRACT : (((B.ERASE !== undefined && B.ERASE !== null) ? B.ERASE : N))), warn: null };
    case "Screen": if (B.SCREEN !== undefined && B.SCREEN !== null) return { blend: B.SCREEN, warn: null }; return { blend: N, warn: "Screen" };
    case "Overlay": if (B.OVERLAY !== undefined && B.OVERLAY !== null) return { blend: B.OVERLAY, warn: null }; return { blend: N, warn: "Overlay" };
    case "Lighten": return { blend: N, warn: "Lighten" };
    default: return { blend: N, warn: null };
  }
};
var blendWarnOnce = function(msg) {
  var w = object.__apfxBlendWarned || (object.__apfxBlendWarned = {});
  if (!w[msg]) { w[msg] = true; console.warn(msg); }
};"""

THREE_BLEND_FOR = """F.threeBlendFor = F.threeBlendFor || function(mode, T) {
  T = T || ((typeof THREE !== "undefined") ? THREE : null);
  var N = (T && T.NormalBlending !== undefined) ? T.NormalBlending : 0;
  var out = { blending: N, equation: null, src: null, dst: null, bake: "normal", warn: null };
  if (!T) return out;
  switch (mode) {
    case "Additive": out.blending = T.AdditiveBlending; out.bake = "additive"; return out;
    case "Subtractive": out.blending = T.SubtractiveBlending; out.bake = "subtractive"; return out;
    case "Multiply": out.blending = T.MultiplyBlending; out.bake = "multiply"; return out;
    case "Screen":
      if (T.CustomBlending === undefined || T.AddEquation === undefined ||
          T.OneFactor === undefined || T.OneMinusSrcColorFactor === undefined)
        { out.warn = "Screen"; return out; }
      out.blending = T.CustomBlending; out.equation = T.AddEquation;
      out.src = T.OneFactor; out.dst = T.OneMinusSrcColorFactor;
      out.bake = "additive"; return out;
    case "Lighten":
      if (T.CustomBlending === undefined || T.MaxEquation === undefined)
        { out.warn = "Lighten"; return out; }
      out.blending = T.CustomBlending; out.equation = T.MaxEquation;
      out.bake = "lighten"; return out;
    case "Overlay": out.warn = "Overlay"; return out;
    default: return out;
  }
};
F.blendWarnOnce = F.blendWarnOnce || function(msg) {
  var w = object.__apfxBlendWarned || (object.__apfxBlendWarned = {});
  if (!w[msg]) { w[msg] = true; console.warn(msg); }
};
F.resolveEmitterBlend = F.resolveEmitterBlend || function(objProp, emitterMode) {
  if (objProp === "JSON" || objProp === "" || objProp === undefined || objProp === null)
    return (typeof emitterMode === "string" && emitterMode) ? emitterMode : "Normal";
  return objProp;
};"""


def main():
    with io.open(EXT, encoding="utf-8") as f:
        raw = f.read()

    if '"Screen"' in raw and 'pixiBlendFor' in raw:
        print("ALREADY-PATCHED")
        return

    # ---- raw-JSON edits: choices, descriptions, comments, version ----
    # (idempotent: each step skips when its output is already present)
    if '"value": "Screen"' not in raw:
        choice_tail = ('            {\n              "label": "",\n'
                       '              "value": "Multiply"\n            }')
        assert raw.count(choice_tail) == 2, "choice tail x%d" % raw.count(choice_tail)
        item = ('\n            {\n              "label": "",\n'
                '              "value": "%s"\n            }')
        choice_new = choice_tail + ''.join(',' + (item % m) for m in NEW_MODES)
        raw = raw.replace(choice_tail, choice_new)
        # sanity: the result must still parse (checked again after all edits)
        json.loads(raw)

    def _supp(want):
        # supplementaryInformation stores the list as an escaped JSON string
        return ('"supplementaryInformation": "'
                + json.dumps(want, separators=(",", ":")).replace('"', '\\"') + '"')

    raw = _ensure(raw, _supp(["JSON", "Normal", "Additive", "Subtractive", "Multiply"]),
                  _supp(["JSON", "Normal", "Additive", "Subtractive", "Multiply"] + NEW_MODES),
                  1, "2D choices")
    raw = _ensure(raw, _supp(["Normal", "Additive", "Subtractive", "Multiply"]),
                  _supp(["Normal", "Additive", "Subtractive", "Multiply"] + NEW_MODES),
                  1, "3D choices")
    raw = _ensure(raw, OLD_DESC, FULL_DESC, 4, "descriptions")
    raw = _ensure(raw,
                  "how particles blend with the background (Normal, Additive, Subtractive, Multiply)",
                  "how particles blend with the background (Normal, Additive, Subtractive, Multiply, Screen, Lighten, Overlay)",
                  1, "blend comment")
    raw = _ensure(raw, '"version": "0.1.1"', '"version": "0.1.2"', 1, "ext version")

    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        f.write(raw)

    doc = json.loads(raw)

    def walk(evts):
        for ev in evts or []:
            if ev.get("type") == "BuiltinCommonInstructions::JsCode":
                code = ev.get("inlineCode", [])
                yield ev, ("\n".join(code) if isinstance(code, list) else str(code))
            for r in walk(ev.get("events", [])):
                yield r

    def chunk_of(name):
        obj = [x for x in doc["eventsBasedObjects"] if x["name"] == name][0]
        hits = []
        for fn in obj.get("eventsFunctions", []):
            hits.extend(list(walk(fn.get("events", []))))
        return hits

    # ---- 2D chunk: pure mapping + warn-once ----
    hits2 = [h for h in chunk_of("AvancedParticleEmitter2D") if "pixiBlendMode" in h[1]]
    assert len(hits2) == 1, "2D blend chunk x%d" % len(hits2)
    ev2, t2 = hits2[0]
    t2 = _rep_once(
        t2,
        "var pixiBlendMode = (function(b){\n"
        "  if (!PIXI || !PIXI.BLEND_MODES) return 0;\n"
        "  switch (b) {\n"
        "    case 'Additive':    return PIXI.BLEND_MODES.ADD;\n"
        "    case 'Multiply':    return PIXI.BLEND_MODES.MULTIPLY;\n"
        "    case 'Subtractive': return (PIXI.BLEND_MODES.SUBTRACT != null ? PIXI.BLEND_MODES.SUBTRACT : (PIXI.BLEND_MODES.ERASE != null ? PIXI.BLEND_MODES.ERASE : PIXI.BLEND_MODES.NORMAL));\n"
        "    default:            return PIXI.BLEND_MODES.NORMAL;\n"
        "  }\n"
        "})(blendingMode);",
        PIXI_BLEND_FOR + "\n"
        "var _pb2 = pixiBlendFor(blendingMode);\n"
        "var pixiBlendMode = _pb2.blend;\n"
        "if (_pb2.warn) blendWarnOnce(\"[AvancedPFX2D] Blend mode '\" + _pb2.warn + \"' is not supported by this PixiJS runtime; falling back to Normal.\");",
        "2D mapping")
    ev2["inlineCode"] = t2.split("\n")

    # ---- 3D chunk: pure mapping + custom blending + fade bake ----
    hits3 = [h for h in chunk_of("AvancedParticleEmitter3D")
             if "F.createMesh = function" in h[1]]
    assert len(hits3) == 1, "3D blend chunk x%d" % len(hits3)
    ev3, t3 = hits3[0]
    t3 = _rep_once(t3, "var F = object.__apfx3DFns;\n\n  F.ease = function(t, easing) {",
                   "var F = object.__apfx3DFns;\n" + THREE_BLEND_FOR + "\n\n  F.ease = function(t, easing) {",
                   "3D helpers")
    t3 = _rep_once(
        t3,
        "var blendMode = THREE.NormalBlending;\n"
        "    if (blending === \"Additive\") blendMode = THREE.AdditiveBlending;\n"
        "    else if (blending === \"Subtractive\") blendMode = THREE.SubtractBlending;\n"
        "    else if (blending === \"Multiply\") blendMode = THREE.MultiplyBlending;",
        "var _br3 = F.threeBlendFor(blending, (typeof THREE !== \"undefined\") ? THREE : null);\n"
        "    if (_br3.warn) F.blendWarnOnce(\"[AvancedPFX3D] Blend mode '\" + _br3.warn + \"' is not supported by this Three.js runtime; falling back to Normal.\");\n"
        "    var blendMode = _br3.blending;",
        "3D mapping")
    t3 = _rep_once(
        t3,
        "child.material.blending = blendMode;",
        "child.material.blending = blendMode;\n"
        "          if (_br3.equation !== null && _br3.equation !== undefined) {\n"
        "            child.material.blendEquation = _br3.equation;\n"
        "            child.material.blendSrc = _br3.src;\n"
        "            child.material.blendDst = _br3.dst;\n"
        "          }",
        "3D GLB equation")
    t3 = _rep_once(
        t3,
        "var imgMesh = new THREE.Mesh(imgGeo, imgMat);",
        "if (_br3.equation !== null && _br3.equation !== undefined) {\n"
        "        imgMat.blendEquation = _br3.equation; imgMat.blendSrc = _br3.src; imgMat.blendDst = _br3.dst;\n"
        "      }\n"
        "      var imgMesh = new THREE.Mesh(imgGeo, imgMat);",
        "3D image equation")
    t3 = _rep_once(
        t3,
        "var mesh = new THREE.Mesh(geo, mat);",
        "if (_br3.equation !== null && _br3.equation !== undefined) {\n"
        "      mat.blendEquation = _br3.equation; mat.blendSrc = _br3.src; mat.blendDst = _br3.dst;\n"
        "    }\n"
        "    var mesh = new THREE.Mesh(geo, mat);",
        "3D primitive equation")
    t3 = _rep_once(
        t3,
        "if (_bm === 'Additive') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = alpha; }",
        "if (_bm === 'Additive' || _bm === 'Screen') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = alpha; }",
        "3D screen bake")
    t3 = _rep_once(
        t3,
        "else if (_bm === 'Subtractive') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }",
        "else if (_bm === 'Subtractive') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }\n"
        "    else if (_bm === 'Lighten') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }",
        "3D lighten bake")
    ev3["inlineCode"] = t3.split("\n")

    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    for label, text in (("2D", t2), ("3D", t3)):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as tf:
            tf.write(text)
            tmp = tf.name
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        os.unlink(tmp)
        assert r.returncode == 0, label + " syntax: " + r.stderr[-2000:]
    print("PATCHED-OK")


if __name__ == "__main__":
    sys.exit(main())
