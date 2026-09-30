# Patches AdvancedParticleEmitter.json (3D runtime) for InstancedMesh
# batching (FPS rescue for weak CPUs: ~580 draw calls -> ~12 buckets).
# Run once; re-runs are a no-op.
#
# Design (visual parity by construction):
#  - Primitive particles (pick.kind === "primitive") draw into per-shape
#    THREE.InstancedMesh buckets (CAP 2048) instead of one Mesh each.
#    Models/images keep the existing pooled-mesh path untouched.
#  - The SAME sampled values feed both paths: instanceColor <- baked
#    (_rM,_gM,_bM), aAlpha attribute <- _aOut, transform via the SAME
#    Object3D method calls in the SAME order -> identical pixels.
#  - Per-instance fade for Normal blending via a tiny onBeforeCompile hook
#    (aAlpha attribute); shared program cache key, no per-mode programs.
#  - Morph flip keeps the classic single-shape swap (no look change);
#    instanced flips only rewrite records, mesh flips reuse the old path
#    (transforms from particle state when no old mesh exists).
#  - Feature-detected (typeof InstancedMesh/InstancedBufferAttribute);
#    F._forceClassic forces the legacy path (test hook + emergency fallback).
#  - Buckets disposed with the object (no GPU leak); materials rebuilt only
#    when blendingMode changes; geometry cloned per bucket (shared geoCache
#    stays clean for individual meshes).
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

DEFS = """F.INST_CAP = 2048;
F.instSupported = function() {
  return (typeof THREE !== "undefined") && THREE &&
    (typeof THREE.InstancedMesh === "function") &&
    (typeof THREE.InstancedBufferAttribute === "function");
};
F.normInstShape = function(shape) {
  var s = String(shape == null ? "circle" : shape).toLowerCase();
  if (s === "sphere" || s === "cube" || s === "diamond" || s === "pyramid" ||
      s === "torus" || s === "square" || s === "triangle" || s === "star" ||
      s === "line" || s === "circle" || s === "billboard") return s;
  return "circle";
};
F.isBillboardShape = function(shape) {
  return !(shape === "sphere" || shape === "cube" || shape === "diamond" ||
           shape === "pyramid" || shape === "torus");
};
F.instAlphaMaterial = function(mat) {
  mat.onBeforeCompile = function(shader) {
    shader.vertexShader = "attribute float aAlpha;\\nvarying float vAlpha;\\n" +
      shader.vertexShader.replace("#include <begin_vertex>",
        "#include <begin_vertex>\\nvAlpha = aAlpha;");
    shader.fragmentShader = "varying float vAlpha;\\n" +
      shader.fragmentShader.replace("#include <color_fragment>",
        "#include <color_fragment>\\ndiffuseColor.a *= vAlpha;");
  };
  mat.customProgramCacheKey = function() { return "apfx-inst-alpha-v1"; };
  return mat;
};
F.ensureInstBuckets = function(data, blendingMode, shadowParams, group) {
  if (!F.instSupported() || !data || !data.particleGroup || !data.geoCache) return { ok: false };
  var doCast = shadowParams ? shadowParams.castShadow : false;
  if (data._inst && data._instBlend === blendingMode) {
    for (var k in data._inst) {
      if (!data._inst.hasOwnProperty(k)) continue;
      data._inst[k].mesh.castShadow = doCast;
      data._inst[k].count = 0;
    }
    return { ok: true };
  }
  if (data._inst) {
    for (var k2 in data._inst) {
      if (!data._inst.hasOwnProperty(k2)) continue;
      var old = data._inst[k2].mesh;
      if (old.parent) old.parent.remove(old);
      old.geometry.dispose();
      old.material.dispose();
    }
  }
  data._inst = {};
  var _br = F.threeBlendFor(blendingMode, (typeof THREE !== "undefined") ? THREE : null);
  var order = ["sphere", "cube", "diamond", "pyramid", "torus", "square", "triangle", "star", "line", "circle", "billboard"];
  for (var oi = 0; oi < order.length; oi++) {
    var key = order[oi];
    var src = data.geoCache[key] || data.geoCache.circle;
    var geo = src.clone();
    var mat = new THREE.MeshStandardMaterial({
      color: 0xffffff, transparent: true, opacity: 1,
      side: THREE.DoubleSide, depthWrite: false, blending: _br.blending
    });
    if (_br.equation !== null && _br.equation !== undefined) {
      mat.blendEquation = _br.equation; mat.blendSrc = _br.src; mat.blendDst = _br.dst;
    }
    F.instAlphaMaterial(mat);
    var im = new THREE.InstancedMesh(geo, mat, F.INST_CAP);
    im.frustumCulled = false;
    im.count = 0;
    im.castShadow = doCast;
    var alpha = new Float32Array(F.INST_CAP);
    geo.setAttribute("aAlpha", new THREE.InstancedBufferAttribute(alpha, 1));
    group.add(im);
    data._inst[key] = { mesh: im, alpha: alpha, count: 0 };
  }
  data._instBlend = blendingMode;
  return { ok: true };
};
F.writeInstance = function(data, shapeKey, x, y, z, s, rx, ry, rz, useBb, bbQuat, useAlign, alignQuat, r, g, b, a) {
  var bk = data._inst ? data._inst[shapeKey] : null;
  if (!bk) return;
  var slot = bk.count++;
  if (slot >= F.INST_CAP) {
    bk.count = F.INST_CAP;
    if (!data._instWarned) { data._instWarned = true; console.warn("[AvancedPFX3D] instance cap reached; some particles hidden."); }
    return;
  }
  var d = F._dummy || (F._dummy = new THREE.Object3D());
  d.position.set(x, y, z);
  if (useBb && bbQuat) { d.quaternion.copy(bbQuat); d.rotateZ(rz || 0); }
  else if (useAlign && alignQuat) { d.quaternion.copy(alignQuat); }
  else { d.rotation.set(rx || 0, ry || 0, rz || 0); }
  var sc = Math.max(s, 0.01);
  d.scale.set(sc, sc, sc);
  d.updateMatrix();
  bk.mesh.setMatrixAt(slot, d.matrix);
  var tc = F._tmpC || (F._tmpC = new THREE.Color());
  tc.setRGB(r, g, b);
  bk.mesh.setColorAt(slot, tc);
  bk.alpha[slot] = a;
};"""


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
    if "F.ensureInstBuckets = F.ensureInstBuckets" in raw:
        print("ALREADY-PATCHED")
        return
    doc = json.loads(raw)
    changed = []
    hits = _chunks_of(doc, "AvancedParticleEmitter3D")
    big = [(ev, t) for ev, t in hits if "F.spawnParticle = function" in t]
    assert len(big) == 1, "runtime chunk x%d" % len(big)
    ev, text = big[0]

    # 1) helper defs before F.ease
    text = _replace_once(
        text,
        "  F.ease = function(t, easing) {",
        DEFS + "\n  F.ease = function(t, easing) {",
        "inst defs")

    # 2) spawn: primitives take no mesh (instanced path), models/images keep pool
    text = _replace_once(
        text,
        "    var pooledHit = F.getPooledParticle(first.shape, pick.kind, pick.id, blending, data);\n"
        "    var mesh = pooledHit ? pooledHit.mesh\n"
        "      : F.createMesh(first.shape, pick.kind, pick.id, data, shadowParams, blending);\n"
        "    if (!mesh) return null;\n"
        "    data.particleGroup.add(mesh);\n"
        "    return {\n"
        "      mesh: mesh, currentShape: first.shape, currentRefKind: pick.kind, currentRefId: pick.id,",
        "    var _isPrim = (pick.kind === \"primitive\") && F.instSupported() && !F._forceClassic;\n"
        "    var mesh = null;\n"
        "    if (!_isPrim) {\n"
        "      var pooledHit = F.getPooledParticle(first.shape, pick.kind, pick.id, blending, data);\n"
        "      mesh = pooledHit ? pooledHit.mesh\n"
        "        : F.createMesh(first.shape, pick.kind, pick.id, data, shadowParams, blending);\n"
        "      if (!mesh) return null;\n"
        "      data.particleGroup.add(mesh);\n"
        "    }\n"
        "    return {\n"
        "      mesh: mesh, inst: _isPrim, lastSize: 0, currentShape: first.shape, currentRefKind: pick.kind, currentRefId: pick.id,",
        "spawn instancing")

    # 3) morph flip: primitive<->primitive rewrites records only
    text = _replace_once(
        text,
        "    if (_need3 !== p.currentShape) {\n"
        "      var _pk3 = (_src3.shape === \"custom\" || _src3.shape === \"billboard\") ? F.pickRef(_src3) : { kind: p.currentRefKind, id: p.currentRefId };\n"
        "      var _blend3 = (typeof blendingMode === \"string\" ? blendingMode : \"Normal\");\n"
        "      var _pooled3 = F.getPooledParticle(_need3, _pk3.kind, _pk3.id, _blend3, data);\n"
        "      var _nm3 = _pooled3 ? _pooled3.mesh\n"
        "        : F.createMesh(_need3, _pk3.kind, _pk3.id, data, (typeof shadowParams !== \"undefined\" ? shadowParams : undefined), _blend3);\n"
        "      if (_nm3) {\n"
        "        _nm3.position.copy(p.mesh.position);\n"
        "        _nm3.rotation.copy(p.mesh.rotation);\n"
        "        _nm3.scale.copy(p.mesh.scale);\n"
        "        data.particleGroup.remove(p.mesh);\n"
        "        p.mesh.visible = false;\n"
        "        if (data.pool.length < 200) data.pool.push({ mesh: p.mesh, currentShape: p.currentShape,\n"
        "          currentRefKind: p.currentRefKind, currentRefId: p.currentRefId,\n"
        "          currentBlending: (p.currentBlending || \"Normal\") });\n"
        "        else F.destroyMesh(p.mesh);\n"
        "        data.particleGroup.add(_nm3);\n"
        "        p.mesh = _nm3;\n"
        "        p.currentShape = _need3; p.currentRefKind = _pk3.kind; p.currentRefId = _pk3.id;\n"
        "        p.currentBlending = _blend3;\n"
        "      }\n"
        "    }",
        "    if (_need3 !== p.currentShape) {\n"
        "      var _pk3 = (_src3.shape === \"custom\" || _src3.shape === \"billboard\") ? F.pickRef(_src3) : { kind: p.currentRefKind, id: p.currentRefId };\n"
        "      var _blend3 = (typeof blendingMode === \"string\" ? blendingMode : \"Normal\");\n"
        "      var _newPrim = (_pk3.kind === \"primitive\") && F.instSupported() && !F._forceClassic;\n"
        "      var _oldPrim = !p.mesh;\n"
        "      if (_newPrim && _oldPrim) {\n"
        "        p.currentShape = _need3; p.currentRefKind = _pk3.kind; p.currentRefId = _pk3.id;\n"
        "        p.currentBlending = _blend3;\n"
        "      } else {\n"
        "        var _pooled3 = (!_newPrim) ? F.getPooledParticle(_need3, _pk3.kind, _pk3.id, _blend3, data) : null;\n"
        "        var _nm3 = _pooled3 ? _pooled3.mesh\n"
        "          : (_newPrim ? null : F.createMesh(_need3, _pk3.kind, _pk3.id, data, (typeof shadowParams !== \"undefined\" ? shadowParams : undefined), _blend3));\n"
        "        if (_nm3 || _newPrim) {\n"
        "          if (_nm3) {\n"
        "            if (p.mesh) {\n"
        "              _nm3.position.copy(p.mesh.position);\n"
        "              _nm3.rotation.copy(p.mesh.rotation);\n"
        "              _nm3.scale.copy(p.mesh.scale);\n"
        "            } else {\n"
        "              _nm3.position.set(p.x, p.y, p.z);\n"
        "              _nm3.rotation.set(p.accRotX || 0, p.accRotY || 0, p.accRotZ || 0);\n"
        "              var _ls3 = Math.max(p.lastSize || 1, 0.01);\n"
        "              _nm3.scale.set(_ls3, _ls3, _ls3);\n"
        "            }\n"
        "          }\n"
        "          if (p.mesh) {\n"
        "            data.particleGroup.remove(p.mesh);\n"
        "            p.mesh.visible = false;\n"
        "            if (data.pool.length < 200) data.pool.push({ mesh: p.mesh, currentShape: p.currentShape,\n"
        "              currentRefKind: p.currentRefKind, currentRefId: p.currentRefId,\n"
        "              currentBlending: (p.currentBlending || \"Normal\") });\n"
        "            else F.destroyMesh(p.mesh);\n"
        "          }\n"
        "          if (_nm3) {\n"
        "            data.particleGroup.add(_nm3);\n"
        "            p.mesh = _nm3;\n"
        "          } else {\n"
        "            p.mesh = null;\n"
        "          }\n"
        "          p.inst = _newPrim;\n"
        "          p.currentShape = _need3; p.currentRefKind = _pk3.kind; p.currentRefId = _pk3.id;\n"
        "          p.currentBlending = _blend3;\n"
        "        }\n"
        "      }\n"
        "    }",
        "flip instancing")

    # 4) draw section: shared sampling stays; writes branch instanced vs mesh
    text = _replace_once(
        text,
        "    p.mesh.position.set(p.x, p.y, p.z);\n"
        "    var s = Math.max(size, 0.01);\n"
        "    p.mesh.scale.set(s, s, s);\n"
        "\n"
        "    // Studio rotation modes: 'speed' (deg/sec integrated) or 'interpolation' (absolute angle).\n"
        "    if (emitter.rotationMode === \"interpolation\") {\n"
        "      p.accRotX = rotX * Math.PI/180;\n"
        "      p.accRotY = rotY * Math.PI/180;\n"
        "      p.accRotZ = rotZ * Math.PI/180;\n"
        "    } else {\n"
        "      p.accRotX = (p.accRotX || 0) + rotX * Math.PI/180 * dt;\n"
        "      p.accRotY = (p.accRotY || 0) + rotY * Math.PI/180 * dt;\n"
        "      p.accRotZ = (p.accRotZ || 0) + rotZ * Math.PI/180 * dt;\n"
        "    }\n"
        "    if (p.mesh.userData.isBillboard && emitter.billboardForced && _bbQuat) {\n"
        "      p.mesh.quaternion.copy(_bbQuat);\n"
        "      p.mesh.rotateZ(p.accRotZ || 0);\n"
        "    } else {\n"
        "      p.mesh.rotation.set(p.accRotX, p.accRotY, p.accRotZ);\n"
        "    }\n"
        "    if (emitter.alignToVelocity && curSpd > 0.001 && !(p.mesh.userData.isBillboard && emitter.billboardForced)) {\n"
        "      var dir3 = F._tv4 || (F._tv4 = new THREE.Vector3());\n"
        "      dir3.set(p.vx, p.vy, p.vz).normalize();\n"
        "      var quat = F._tq2 || (F._tq2 = new THREE.Quaternion());\n"
        "      var mat4 = F._tm2 || (F._tm2 = new THREE.Matrix4());\n"
        "      var _zero3 = F._tv5 || (F._tv5 = new THREE.Vector3());\n"
        "      var _up3 = F._tv6 || (F._tv6 = new THREE.Vector3(0, 0, 1));\n"
        "      mat4.lookAt(_zero3.set(0, 0, 0), dir3, _up3.set(0, 0, 1));\n"
        "      quat.setFromRotationMatrix(mat4);\n"
        "      var spinEuler = F._te1 || (F._te1 = new THREE.Euler(0, 0, 0, 'XYZ'));\n"
        "      spinEuler.set(p.accRotX || 0, p.accRotY || 0, p.accRotZ || 0);\n"
        "      var spinQuat = F._tq3 || (F._tq3 = new THREE.Quaternion());\n"
        "      spinQuat.setFromEuler(spinEuler);\n"
        "      p.mesh.quaternion.copy(quat).multiply(spinQuat);\n"
        "    }\n"
        "\n"
        "    var threeColor = F.numToThreeColor(col);\n"
        "    var alpha = Math.max(0, Math.min(1, opacity / 255));\n"
        "    // Blending-aware modulation: Multiply/Subtractive ignore srcAlpha at the GL level,\n"
        "    // and Additive only modulates RGB via srcAlpha. To make opacity visually fade\n"
        "    // particles for ALL blending modes, we bake the fade into the color channel.\n"
        "    var _bm = (typeof blendingMode === 'string') ? blendingMode : 'Normal';\n"
        "    var _rM = threeColor.r, _gM = threeColor.g, _bM = threeColor.b, _aOut = alpha;\n"
        "    if (_bm === 'Additive' || _bm === 'Screen') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = alpha; }\n"
        "    else if (_bm === 'Multiply') { _rM = 1 + (threeColor.r - 1) * alpha; _gM = 1 + (threeColor.g - 1) * alpha; _bM = 1 + (threeColor.b - 1) * alpha; _aOut = 1; }\n"
        "    else if (_bm === 'Subtractive') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }\n"
        "    else if (_bm === 'Lighten') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }\n"
        "    if (p.mesh.userData.isGLB) {\n"
        "      p.mesh.traverse(function(c){ if (c.isMesh && c.material) { c.material.opacity = _aOut; if (c.material.color) { var bt = c.material.userData.baseTint || [1, 1, 1]; c.material.color.setRGB(bt[0] * _rM, bt[1] * _gM, bt[2] * _bM); } } });\n"
        "    } else {\n"
        "      if (p.mesh.material) { p.mesh.material.color.setRGB(_rM, _gM, _bM); p.mesh.material.opacity = _aOut; }\n"
        "    }",
        "    var s = Math.max(size, 0.01);\n"
        "    p.lastSize = s;\n"
        "\n"
        "    // Studio rotation modes: 'speed' (deg/sec integrated) or 'interpolation' (absolute angle).\n"
        "    if (emitter.rotationMode === \"interpolation\") {\n"
        "      p.accRotX = rotX * Math.PI/180;\n"
        "      p.accRotY = rotY * Math.PI/180;\n"
        "      p.accRotZ = rotZ * Math.PI/180;\n"
        "    } else {\n"
        "      p.accRotX = (p.accRotX || 0) + rotX * Math.PI/180 * dt;\n"
        "      p.accRotY = (p.accRotY || 0) + rotY * Math.PI/180 * dt;\n"
        "      p.accRotZ = (p.accRotZ || 0) + rotZ * Math.PI/180 * dt;\n"
        "    }\n"
        "    var _shpI = null;\n"
        "    var _isBb = p.mesh && p.mesh.userData.isBillboard;\n"
        "    if (p.inst) {\n"
        "      _shpI = F.normInstShape(p.currentShape);\n"
        "      _isBb = F.isBillboardShape(_shpI);\n"
        "    }\n"
        "    var _useBb = _isBb && emitter.billboardForced && _bbQuat;\n"
        "    var _useAlign = emitter.alignToVelocity && curSpd > 0.001 && !(_isBb && emitter.billboardForced);\n"
        "    var quat = null;\n"
        "    if (_useAlign) {\n"
        "      var dir3 = F._tv4 || (F._tv4 = new THREE.Vector3());\n"
        "      dir3.set(p.vx, p.vy, p.vz).normalize();\n"
        "      quat = F._tq2 || (F._tq2 = new THREE.Quaternion());\n"
        "      var mat4 = F._tm2 || (F._tm2 = new THREE.Matrix4());\n"
        "      var _zero3 = F._tv5 || (F._tv5 = new THREE.Vector3());\n"
        "      var _up3 = F._tv6 || (F._tv6 = new THREE.Vector3(0, 0, 1));\n"
        "      mat4.lookAt(_zero3.set(0, 0, 0), dir3, _up3.set(0, 0, 1));\n"
        "      quat.setFromRotationMatrix(mat4);\n"
        "      var spinEuler = F._te1 || (F._te1 = new THREE.Euler(0, 0, 0, 'XYZ'));\n"
        "      spinEuler.set(p.accRotX || 0, p.accRotY || 0, p.accRotZ || 0);\n"
        "      var spinQuat = F._tq3 || (F._tq3 = new THREE.Quaternion());\n"
        "      spinQuat.setFromEuler(spinEuler);\n"
        "      var _alq = quat;\n"
        "      quat = F._tq4 || (F._tq4 = new THREE.Quaternion());\n"
        "      quat.copy(_alq).multiply(spinQuat);\n"
        "    }\n"
        "\n"
        "    var threeColor = F.numToThreeColor(col);\n"
        "    var alpha = Math.max(0, Math.min(1, opacity / 255));\n"
        "    // Blending-aware modulation: Multiply/Subtractive ignore srcAlpha at the GL level,\n"
        "    // and Additive only modulates RGB via srcAlpha. To make opacity visually fade\n"
        "    // particles for ALL blending modes, we bake the fade into the color channel.\n"
        "    var _bm = (typeof blendingMode === 'string') ? blendingMode : 'Normal';\n"
        "    var _rM = threeColor.r, _gM = threeColor.g, _bM = threeColor.b, _aOut = alpha;\n"
        "    if (_bm === 'Additive' || _bm === 'Screen') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = alpha; }\n"
        "    else if (_bm === 'Multiply') { _rM = 1 + (threeColor.r - 1) * alpha; _gM = 1 + (threeColor.g - 1) * alpha; _bM = 1 + (threeColor.b - 1) * alpha; _aOut = 1; }\n"
        "    else if (_bm === 'Subtractive') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }\n"
        "    else if (_bm === 'Lighten') { _rM = threeColor.r * alpha; _gM = threeColor.g * alpha; _bM = threeColor.b * alpha; _aOut = 1; }\n"
        "    if (p.inst) {\n"
        "      F.writeInstance(data, _shpI, p.x, p.y, p.z, s, p.accRotX, p.accRotY, p.accRotZ,\n"
        "        _useBb, _bbQuat, _useAlign, quat, _rM, _gM, _bM, _aOut);\n"
        "    } else if (p.mesh) {\n"
        "      p.mesh.position.set(p.x, p.y, p.z);\n"
        "      p.mesh.scale.set(s, s, s);\n"
        "      if (_useBb) {\n"
        "        p.mesh.quaternion.copy(_bbQuat);\n"
        "        p.mesh.rotateZ(p.accRotZ || 0);\n"
        "      } else {\n"
        "        p.mesh.rotation.set(p.accRotX, p.accRotY, p.accRotZ);\n"
        "      }\n"
        "      if (_useAlign) {\n"
        "        p.mesh.quaternion.copy(quat).multiply(spinQuat);\n"
        "      }\n"
        "      if (p.mesh.userData.isGLB) {\n"
        "        p.mesh.traverse(function(c){ if (c.isMesh && c.material) { c.material.opacity = _aOut; if (c.material.color) { var bt = c.material.userData.baseTint || [1, 1, 1]; c.material.color.setRGB(bt[0] * _rM, bt[1] * _gM, bt[2] * _bM); } } });\n"
        "      } else {\n"
        "        if (p.mesh.material) { p.mesh.material.color.setRGB(_rM, _gM, _bM); p.mesh.material.opacity = _aOut; }\n"
        "      }\n"
        "    }",
        "draw instancing")

    # 5) recycle/dispose null-safety (instanced particles own no mesh)
    text = _replace_once(
        text,
        "  F.recycleParticle = function(p, data) {\n"
        "    F.disposeMesh(p.mesh, data.particleGroup);",
        "  F.recycleParticle = function(p, data) {\n"
        "    if (!p.mesh) return;\n"
        "    F.disposeMesh(p.mesh, data.particleGroup);",
        "recycle guard")
    text = _replace_once(
        text,
        "  F.disposeMesh = function(mesh, group) {\n"
        "    group.remove(mesh);\n"
        "    mesh.visible = false;\n"
        "  };",
        "  F.disposeMesh = function(mesh, group) {\n"
        "    if (!mesh) return;\n"
        "    group.remove(mesh);\n"
        "    mesh.visible = false;\n"
        "  };",
        "dispose guard")
    # NOTE: the object-cleanup loop already guards null meshes
    # (`if (data.particles[ci].mesh)`); bucket disposal goes below.
    text = _replace_once(
        text,
        "  if (data.particleGroup && data.particleGroup.parent) data.particleGroup.parent.remove(data.particleGroup);\n"
        "  data.particles = [];\n"
        "  object.__apfx3D = null;",
        "  if (data.particleGroup && data.particleGroup.parent) data.particleGroup.parent.remove(data.particleGroup);\n"
        "  if (data._inst) {\n"
        "    for (var _dk in data._inst) {\n"
        "      if (!data._inst.hasOwnProperty(_dk)) continue;\n"
        "      var _dm = data._inst[_dk].mesh;\n"
        "      if (_dm.parent) _dm.parent.remove(_dm);\n"
        "      _dm.geometry.dispose();\n"
        "      _dm.material.dispose();\n"
        "    }\n"
        "    data._inst = null;\n"
        "  }\n"
        "  data.particles = [];\n"
        "  object.__apfx3D = null;",
        "cleanup buckets")

    # 6) bucket ensure at update start + finalize after the loop
    text = _replace_once(
        text,
        "// Update particles\n"
        "  var _fOn = F.fieldsActive(data.emitter.fields);",
        "// Update particles\n"
        "  var _fOn = F.fieldsActive(data.emitter.fields);\n"
        "  var _instOk = F.ensureInstBuckets(data, blendingMode, shadowParams, data.particleGroup);",
        "ensure call")
    text = _replace_once(
        text,
        "// Toggle particle rendering (simulation continues regardless)",
        "if (data._inst) {\n"
        "  for (var _bk in data._inst) {\n"
        "    if (!data._inst.hasOwnProperty(_bk)) continue;\n"
        "    var _bd = data._inst[_bk];\n"
        "    _bd.mesh.count = _bd.count;\n"
        "    _bd.mesh.instanceMatrix.needsUpdate = true;\n"
        "    if (_bd.mesh.instanceColor) _bd.mesh.instanceColor.needsUpdate = true;\n"
        "    var _aa = _bd.mesh.geometry.getAttribute(\"aAlpha\");\n"
        "    if (_aa) _aa.needsUpdate = true;\n"
        "  }\n"
        "}\n"
        "\n"
        "// Toggle particle rendering (simulation continues regardless)",
        "finalize buckets")

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
