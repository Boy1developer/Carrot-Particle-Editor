# Patches AdvancedParticleEmitter.json (3D runtime) for multi-instance scale
# and sampling diet (follow-up to patch_instancing.py). Run once; no-op after.
#
# 1. Lazy buckets: buckets are created on first write per shape instead of
#    all 11 upfront (N emitter instances x 11 empty buckets = hundreds of
#    wasted draw calls + ~170KB GPU/CPU each). F.getBucket creates on demand;
#    F.ensureInstBuckets keeps blend-change rebuild + per-frame sync.
# 2. Empty buckets hidden (visible=false): zero render cost when idle.
# 3. Sampling diet (exact values preserved): buildTracks tags constant
#    tracks (arr._static) and pre-parsed color ints (color._rgb);
#    sampleTrack/sampleColorTrack take the fast path. F._dietOff forces the
#    legacy path (test hook; appearance must be bit-identical either way).
#
# Anchors assert single occurrence; the modified chunk passes node --check
# (wrapped in a function since chunks may contain bare `return`).
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")


def _replace_once(text, old, new, what):
    assert text.count(old) == 1, "%s anchor x%d" % (what, text.count(old))
    return text.replace(old, new, 1)


def _walk(evts):
    for ev in evts or []:
        if ev.get('type') == 'BuiltinCommonInstructions::JsCode':
            code = ev.get('inlineCode', [])
            text = "\n".join(code) if isinstance(code, list) else str(code)
            yield ev, text
        for r in _walk(ev.get('events', [])):
            yield r


def _chunks_of(doc, name):
    obj = [x for x in doc["eventsBasedObjects"] if x["name"] == name][0]
    hits = []
    for fn in obj.get("eventsFunctions", []):
        hits.extend(list(_walk(fn.get("events", []))))
    return hits


def main():
    with io.open(EXT, encoding="utf-8") as f:
        raw = f.read()
    if "F.getBucket = F.getBucket" in raw:
        print("ALREADY-PATCHED")
        return
    doc = json.loads(raw)
    changed = []
    hits = _chunks_of(doc, "AvancedParticleEmitter3D")
    big = [(ev, t) for ev, t in hits if "F.ensureInstBuckets = function" in t]
    assert len(big) == 1, "runtime chunk x%d" % len(big)
    ev, text = big[0]

    # 1) ensure: drop the eager 11-bucket build; stash refs for lazy create
    text = _replace_once(
        text,
        "  data._inst = {};\n"
        "  var _br = F.threeBlendFor(blendingMode, (typeof THREE !== \"undefined\") ? THREE : null);\n"
        "  var order = [\"sphere\", \"cube\", \"diamond\", \"pyramid\", \"torus\", \"square\", \"triangle\", \"star\", \"line\", \"circle\", \"billboard\"];\n"
        "  for (var oi = 0; oi < order.length; oi++) {\n"
        "    var key = order[oi];\n"
        "    var src = data.geoCache[key] || data.geoCache.circle;\n"
        "    var geo = src.clone();\n"
        "    var mat = new THREE.MeshStandardMaterial({\n"
        "      color: 0xffffff, transparent: true, opacity: 1,\n"
        "      side: THREE.DoubleSide, depthWrite: false, blending: _br.blending\n"
        "    });\n"
        "    if (_br.equation !== null && _br.equation !== undefined) {\n"
        "      mat.blendEquation = _br.equation; mat.blendSrc = _br.src; mat.blendDst = _br.dst;\n"
        "    }\n"
        "    F.instAlphaMaterial(mat);\n"
        "    var im = new THREE.InstancedMesh(geo, mat, F.INST_CAP);\n"
        "    im.frustumCulled = false;\n"
        "    im.count = 0;\n"
        "    im.castShadow = doCast;\n"
        "    var alpha = new Float32Array(F.INST_CAP);\n"
        "    geo.setAttribute(\"aAlpha\", new THREE.InstancedBufferAttribute(alpha, 1));\n"
        "    group.add(im);\n"
        "    data._inst[key] = { mesh: im, alpha: alpha, count: 0 };\n"
        "  }\n"
        "  data._instBlend = blendingMode;\n"
        "  return { ok: true };\n"
        "};",
        "  data._inst = {};\n"
        "  data._instBlend = blendingMode;\n"
        "  data._instGroup = group;\n"
        "  data._instShadow = shadowParams || null;\n"
        "  return { ok: true };\n"
        "};\n"
        "F.getBucket = function(data, shapeKey) {\n"
        "  var bk = (data._inst && data._inst[shapeKey]) || null;\n"
        "  if (bk) return bk;\n"
        "  if (!F.instSupported() || !data || !data.particleGroup || !data.geoCache) return null;\n"
        "  if (!data._inst) data._inst = {};\n"
        "  var group = data._instGroup || data.particleGroup;\n"
        "  var shadowParams = data._instShadow;\n"
        "  var _br = F.threeBlendFor(data._instBlend, (typeof THREE !== \"undefined\") ? THREE : null);\n"
        "  if (_br.warn) F.blendWarnOnce(\"[AvancedPFX3D] Blend mode '\" + _br.warn + \"' is not supported by this Three.js runtime; falling back to Normal.\");\n"
        "  var src = data.geoCache[shapeKey] || data.geoCache.circle;\n"
        "  var geo = src.clone();\n"
        "  var mat = new THREE.MeshStandardMaterial({\n"
        "    color: 0xffffff, transparent: true, opacity: 1,\n"
        "    side: THREE.DoubleSide, depthWrite: false, blending: _br.blending\n"
        "  });\n"
        "  if (_br.equation !== null && _br.equation !== undefined) {\n"
        "    mat.blendEquation = _br.equation; mat.blendSrc = _br.src; mat.blendDst = _br.dst;\n"
        "  }\n"
        "  F.instAlphaMaterial(mat);\n"
        "  var im = new THREE.InstancedMesh(geo, mat, F.INST_CAP);\n"
        "  im.frustumCulled = false;\n"
        "  im.count = 0;\n"
        "  im.visible = false;\n"
        "  im.castShadow = shadowParams ? shadowParams.castShadow : false;\n"
        "  var alpha = new Float32Array(F.INST_CAP);\n"
        "  geo.setAttribute(\"aAlpha\", new THREE.InstancedBufferAttribute(alpha, 1));\n"
        "  group.add(im);\n"
        "  bk = { mesh: im, alpha: alpha, count: 0 };\n"
        "  data._inst[shapeKey] = bk;\n"
        "  return bk;\n"
        "};",
        "lazy buckets")

    # 2) writeInstance resolves through the lazy getter
    text = _replace_once(
        text,
        "F.writeInstance = function(data, shapeKey, x, y, z, s, rx, ry, rz, useBb, bbQuat, useAlign, alignQuat, r, g, b, a) {\n"
        "  var bk = data._inst ? data._inst[shapeKey] : null;\n"
        "  if (!bk) return;",
        "F.writeInstance = function(data, shapeKey, x, y, z, s, rx, ry, rz, useBb, bbQuat, useAlign, alignQuat, r, g, b, a) {\n"
        "  var bk = F.getBucket(data, shapeKey);\n"
        "  if (!bk) return;",
        "lazy write")

    # 3) finalize hides empty buckets (zero render cost when idle)
    text = _replace_once(
        text,
        "    _bd.mesh.count = _bd.count;\n"
        "    _bd.mesh.instanceMatrix.needsUpdate = true;",
        "    _bd.mesh.count = _bd.count;\n"
        "    _bd.mesh.visible = (_bd.count > 0);\n"
        "    _bd.mesh.instanceMatrix.needsUpdate = true;",
        "empty hidden")

    # 4) track tagging helper + call at buildTracks return
    text = _replace_once(
        text,
        "  F.buildTracks = function(kf, rotMode) {",
        "  F.tagTracks = function(T) {\n"
        "    for (var tk in T) {\n"
        "      if (!T.hasOwnProperty(tk)) continue;\n"
        "      var arr = T[tk];\n"
        "      if (!arr || !arr.length) continue;\n"
        "      var allSame = true;\n"
        "      for (var qi = 1; qi < arr.length; qi++) {\n"
        "        if (arr[qi].v !== arr[0].v) { allSame = false; break; }\n"
        "      }\n"
        "      if (allSame) arr._static = arr[0].v;\n"
        "    }\n"
        "    if (T.color && T.color.length) {\n"
        "      var ok = true, rgb = [];\n"
        "      for (var ci = 0; ci < T.color.length; ci++) {\n"
        "        var m = /^#?([0-9a-fA-F]{6})$/.exec(String(T.color[ci].v || \"\"));\n"
        "        if (!m) { ok = false; break; }\n"
        "        var n = parseInt(m[1], 16);\n"
        "        rgb.push([(n >> 16) & 255, (n >> 8) & 255, n & 255]);\n"
        "      }\n"
        "      if (ok) T.color._rgb = rgb;\n"
        "    }\n"
        "    return T;\n"
        "  };\n"
        "  F.buildTracks = function(kf, rotMode) {",
        "tag def")
    text = _replace_once(
        text,
        "    return { baseT: baseT, T: T };",
        "    F.tagTracks(T);\n"
        "    return { baseT: baseT, T: T };",
        "tag call")

    # 5) sampleTrack static fast path
    text = _replace_once(
        text,
        "  F.sampleTrack = function(kfs, t, fb) {\n"
        "    if (!kfs || !kfs.length) return fb;",
        "  F.sampleTrack = function(kfs, t, fb) {\n"
        "    if (!kfs || !kfs.length) return fb;\n"
        "    if (!F._dietOff && kfs._static !== undefined) return kfs._static;",
        "sample static")

    # 6) sampleColorTrack pre-parsed fast path (same math, zero string work)
    text = _replace_once(
        text,
        "  F.sampleColorTrack = function(kfs, t, fb) {\n"
        "    if (!kfs || !kfs.length) return F.hexToRgb(fb || '#ffffff');",
        "  F.sampleColorTrack = function(kfs, t, fb) {\n"
        "    if (!kfs || !kfs.length) return F.hexToRgb(fb || '#ffffff');\n"
        "    if (!F._dietOff && kfs._rgb) {\n"
        "      var R = kfs._rgb, _c0, _c1, _e = 0;\n"
        "      if (R.length === 1 || t <= kfs[0].t) { _c0 = R[0]; _c1 = R[0]; }\n"
        "      else if (t >= kfs[kfs.length-1].t) { _c0 = R[R.length-1]; _c1 = _c0; }\n"
        "      else {\n"
        "        _c0 = R[0]; _c1 = R[0];\n"
        "        for (var i = 0; i < kfs.length-1; i++) {\n"
        "          var a = kfs[i], b = kfs[i+1];\n"
        "          if (t >= a.t && t <= b.t) {\n"
        "            var span = b.t - a.t;\n"
        "            _e = F.ease(span > 0 ? (t - a.t) / span : 0, a.e);\n"
        "            _c0 = R[i]; _c1 = R[i+1];\n"
        "            break;\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "      return { r: Math.round(_c0[0] + (_c1[0] - _c0[0]) * _e),\n"
        "               g: Math.round(_c0[1] + (_c1[1] - _c0[1]) * _e),\n"
        "               b: Math.round(_c0[2] + (_c1[2] - _c0[2]) * _e) };\n"
        "    }",
        "sample rgb")

    ev["inlineCode"] = text.split("\n")
    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    for label, text in (("3D runtime", text),):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as tf:
            tf.write("function __chk(){\n" + text + "\n}")
            tmp = tf.name
        r = subprocess.run(["node", "--check", tmp],
                           capture_output=True, text=True)
        os.unlink(tmp)
        assert r.returncode == 0, label + ": " + r.stderr[-2000:]
    print("PATCHED-OK")


if __name__ == "__main__":
    sys.exit(main())
