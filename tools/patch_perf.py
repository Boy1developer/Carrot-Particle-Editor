# Patches AdvancedParticleEmitter.json (3D runtime, doStepPostEvents) for
# rendering efficiency (Phase 5). Run once; re-runs are a no-op.
#
#  1. Mesh pool is actually USED: getPooledParticle existed but had zero call
#     sites (every spawn created fresh meshes + cloned materials). Spawns and
#     morph-flips now take a pooled mesh when one matches, fixing steady-state
#     per-spawn GPU/shader churn (and a GLB leak: flipped-away GLB meshes were
#     removed but never disposed or pooled).
#  2. Pool/mesh cache key includes blendingMode from the start (a pooled mesh
#     keeps the blending it was created with; materials are never shared
#     across blend modes).
#  3. Per-frame THREE allocations hoisted to lazy F-level temps (billboard
#     basis, alignToVelocity quaternion chain, numToThreeColor scratch).
#
# Anchors assert single occurrence; the modified chunk passes node --check.
import io
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")


def _replace_once(chunk, old, new):
    assert chunk.count(old) == 1, "anchor x%d: %r" % (chunk.count(old), old[:70])
    return chunk.replace(old, new, 1)


def main():
    with io.open(EXT, encoding="utf-8") as f:
        doc = json.load(f)
    obj = [x for x in doc["eventsBasedObjects"]
           if x["name"] == "AvancedParticleEmitter3D"][0]

    def walk(evts):
        for ev in evts or []:
            if ev.get("type") == "BuiltinCommonInstructions::JsCode":
                code = ev.get("inlineCode", [])
                text = "\n".join(code) if isinstance(code, list) else str(code)
                if "F.spawnParticle = function" in text and "F.createMesh = function" in text:
                    yield ev, text
            for r in walk(ev.get("events", [])):
                yield r

    hits = []
    for fn in obj.get("eventsFunctions", []):
        hits.extend(list(walk(fn.get("events", []))))
    assert len(hits) == 1, "expected 1 runtime chunk, got %d" % len(hits)
    ev, text = hits[0]
    if "pooledHit" in text:
        print("ALREADY-PATCHED")
        return

    # 1) pool key gains blending (never share materials across blend modes)
    text = _replace_once(
        text,
        "F.getPooledParticle = function(shape, refKind, refId, data) {\n"
        "    for (var i = data.pool.length - 1; i >= 0; i--) {\n"
        "      var p = data.pool[i];\n"
        "      if (p.currentShape === shape && p.currentRefKind === refKind && p.currentRefId === refId) {",
        "F.getPooledParticle = function(shape, refKind, refId, blending, data) {\n"
        "    var blendKey = (typeof blending === \"string\" && blending) ? blending : \"Normal\";\n"
        "    for (var i = data.pool.length - 1; i >= 0; i--) {\n"
        "      var p = data.pool[i];\n"
        "      if (p.currentShape === shape && p.currentRefKind === refKind && p.currentRefId === refId &&\n"
        "          (p.currentBlending || \"Normal\") === blendKey) {")

    # 2) spawn reuses pooled meshes (steady state: zero mesh/material churn)
    text = _replace_once(
        text,
        "var mesh = F.createMesh(first.shape, pick.kind, pick.id, data, shadowParams, blending);",
        "var pooledHit = F.getPooledParticle(first.shape, pick.kind, pick.id, blending, data);\n"
        "    var mesh = pooledHit ? pooledHit.mesh\n"
        "      : F.createMesh(first.shape, pick.kind, pick.id, data, shadowParams, blending);")
    text = _replace_once(
        text,
        "mesh: mesh, currentShape: first.shape, currentRefKind: pick.kind, currentRefId: pick.id,",
        "mesh: mesh, currentShape: first.shape, currentRefKind: pick.kind, currentRefId: pick.id,\n"
        "      currentBlending: (typeof blending === \"string\" && blending) ? blending : \"Normal\",")

    # 3) morph-flip reuses pooled meshes too; old mesh returns to the pool
    #    (previously: fresh mesh every flip + GLB meshes leaked entirely)
    text = _replace_once(
        text,
        "var _nm3 = F.createMesh(_need3, _pk3.kind, _pk3.id, data, (typeof shadowParams !== \"undefined\" ? shadowParams : undefined), (typeof blendingMode === \"string\" ? blendingMode : \"Normal\"));",
        "var _blend3 = (typeof blendingMode === \"string\" ? blendingMode : \"Normal\");\n"
        "      var _pooled3 = F.getPooledParticle(_need3, _pk3.kind, _pk3.id, _blend3, data);\n"
        "      var _nm3 = _pooled3 ? _pooled3.mesh\n"
        "        : F.createMesh(_need3, _pk3.kind, _pk3.id, data, (typeof shadowParams !== \"undefined\" ? shadowParams : undefined), _blend3);")
    text = _replace_once(
        text,
        "data.particleGroup.remove(p.mesh);\n"
        "        if (!p.mesh.userData.isGLB && p.mesh.material && p.mesh.material.dispose) p.mesh.material.dispose();",
        "data.particleGroup.remove(p.mesh);\n"
        "        p.mesh.visible = false;\n"
        "        if (data.pool.length < 200) data.pool.push({ mesh: p.mesh, currentShape: p.currentShape,\n"
        "          currentRefKind: p.currentRefKind, currentRefId: p.currentRefId,\n"
        "          currentBlending: (p.currentBlending || \"Normal\") });\n"
        "        else F.destroyMesh(p.mesh);")
    text = _replace_once(
        text,
        "p.currentShape = _need3; p.currentRefKind = _pk3.kind; p.currentRefId = _pk3.id;",
        "p.currentShape = _need3; p.currentRefKind = _pk3.kind; p.currentRefId = _pk3.id;\n"
        "        p.currentBlending = _blend3;")

    # 4) per-frame THREE temps: billboard basis (once per frame) ...
    text = _replace_once(
        text,
        "var camRight = new THREE.Vector3(ve[0], ve[4], ve[8]);\n"
        "    var camUp    = new THREE.Vector3(ve[1], ve[5], ve[9]);\n"
        "    var camBack  = new THREE.Vector3(ve[2], ve[6], ve[10]);",
        "var camRight = F._tv1 || (F._tv1 = new THREE.Vector3());\n"
        "    var camUp    = F._tv2 || (F._tv2 = new THREE.Vector3());\n"
        "    var camBack  = F._tv3 || (F._tv3 = new THREE.Vector3());\n"
        "    camRight.set(ve[0], ve[4], ve[8]);\n"
        "    camUp.set(ve[1], ve[5], ve[9]);\n"
        "    camBack.set(ve[2], ve[6], ve[10]);")
    text = _replace_once(
        text,
        "var _bbMat = new THREE.Matrix4();\n"
        "    _bbMat.makeBasis(camRight, camUp, camBack);\n"
        "    _bbQuat = new THREE.Quaternion();\n"
        "    _bbQuat.setFromRotationMatrix(_bbMat);",
        "var _bbMat = F._tm1 || (F._tm1 = new THREE.Matrix4());\n"
        "    _bbMat.makeBasis(camRight, camUp, camBack);\n"
        "    _bbQuat = F._tq1 || (F._tq1 = new THREE.Quaternion());\n"
        "    _bbQuat.setFromRotationMatrix(_bbMat);")

    # ... align-to-velocity chain (per particle) ...
    text = _replace_once(
        text,
        "var dir3 = new THREE.Vector3(p.vx, p.vy, p.vz).normalize();\n"
        "      var quat = new THREE.Quaternion();\n"
        "      var mat4 = new THREE.Matrix4();\n"
        "      mat4.lookAt(new THREE.Vector3(), dir3, new THREE.Vector3(0, 0, 1));\n"
        "      quat.setFromRotationMatrix(mat4);\n"
        "      var spinEuler = new THREE.Euler(p.accRotX || 0, p.accRotY || 0, p.accRotZ || 0, 'XYZ');\n"
        "      var spinQuat = new THREE.Quaternion().setFromEuler(spinEuler);",
        "var dir3 = F._tv4 || (F._tv4 = new THREE.Vector3());\n"
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
        "      spinQuat.setFromEuler(spinEuler);")

    # ... and the per-particle color scratch
    text = _replace_once(
        text,
        "F.numToThreeColor = function(c) { return new THREE.Color(c.r/255, c.g/255, c.b/255); };",
        "F.numToThreeColor = function(c) {\n"
        "    var t = F._tmpColor || (F._tmpColor = new THREE.Color(0, 0, 0));\n"
        "    t.setRGB(c.r/255, c.g/255, c.b/255); return t; };")

    ev["inlineCode"] = text.split("\n")
    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    # syntax-check the modified chunk (syntax only; THREE/gdjs are runtime)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as tf:
        tf.write(text)
        tmp = tf.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    assert r.returncode == 0, r.stderr[-2000:]
    print("PATCHED-OK")


if __name__ == "__main__":
    sys.exit(main())
