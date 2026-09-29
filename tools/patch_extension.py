# Patches AdvancedParticleEmitter.json (3D runtime, doStepPostEvents):
#  1. Whole-file model refs (empty node name) resolve to the full GLB scene
#     instead of warning "node not found".
#  2. Skinned meshes are baked to rest pose at load (port of the preview's
#     bakeSkinnedMeshes): pooled clone(true) shares a skeleton whose bones
#     may never update, crumpling rigged GLBs in-game.
# Anchors assert single occurrence; json round-trip is byte-stable otherwise.
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "AdvancedParticleEmitter.json")

BAKE_FN = """\
  // Collapse SkinnedMeshes to static meshes baked in rest pose.
  // Pooled particles clone the template (clone(true)), and a plain clone
  // shares the source skeleton whose bones may never enter the scene, so
  // rigged GLBs render crumpled or invisible. Particles never animate
  // bones, so baking once at load is exact. Port of the preview bake.
  function apfxBakeSkinned(root) {
    root.updateMatrixWorld(true);
    var swaps = [];
    var v = new THREE.Vector3();
    var blend = new THREE.Matrix4(), tmpM = new THREE.Matrix4();
    var full = new THREE.Matrix4(), nm = new THREE.Matrix3();
    var n = new THREE.Vector3();
    root.traverse(function (o) {
      var sk = o;
      if (!sk.isSkinnedMesh || !sk.skeleton) return;
      var geo = sk.geometry;
      var pos = geo.getAttribute("position");
      var sIdx = geo.getAttribute("skinIndex");
      var sW = geo.getAttribute("skinWeight");
      if (!pos || !sIdx || !sW) return;
      var bones = sk.skeleton.bones, inv = sk.skeleton.boneInverses;
      var nb = Math.min(bones.length, inv.length);
      if (nb <= 0) return;
      var out = new Float32Array(pos.count * 3);
      var nrm = geo.getAttribute("normal");
      var outN = nrm ? new Float32Array(nrm.count * 3) : null;
      for (var i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i);
        v.applyMatrix4(sk.bindMatrix);
        var be = blend.elements, e, j;
        for (e = 0; e < 16; e++) be[e] = 0;
        for (j = 0; j < 4; j++) {
          var w = sW.getComponent(i, j);
          if (!w) continue;
          var b = sIdx.getComponent(i, j) | 0;
          if (b < 0) b = 0; else if (b >= nb) b = nb - 1;
          tmpM.multiplyMatrices(bones[b].matrixWorld, inv[b]);
          var te = tmpM.elements;
          for (e = 0; e < 16; e++) be[e] += w * te[e];
        }
        v.applyMatrix4(blend).applyMatrix4(sk.bindMatrixInverse);
        out[i * 3] = v.x; out[i * 3 + 1] = v.y; out[i * 3 + 2] = v.z;
        if (outN && nrm) {
          full.multiplyMatrices(sk.bindMatrixInverse, blend)
            .multiply(sk.bindMatrix);
          nm.getNormalMatrix(full);
          n.fromBufferAttribute(nrm, i).applyMatrix3(nm).normalize();
          outN[i * 3] = n.x; outN[i * 3 + 1] = n.y; outN[i * 3 + 2] = n.z;
        }
      }
      var geo2 = geo.clone();
      geo2.setAttribute("position", new THREE.BufferAttribute(out, 3));
      if (outN) geo2.setAttribute("normal",
        new THREE.BufferAttribute(outN, 3));
      geo2.morphAttributes = {};
      geo2.computeBoundingSphere();
      geo2.computeBoundingBox();
      var mesh = new THREE.Mesh(geo2, sk.material);
      mesh.position.copy(sk.position);
      mesh.quaternion.copy(sk.quaternion);
      mesh.scale.copy(sk.scale);
      mesh.name = sk.name;
      if (sk.parent) {
        swaps.push({ p: sk.parent,
          i: sk.parent.children.indexOf(sk), m: mesh });
        geo.dispose();
      }
    });
    for (var k = 0; k < swaps.length; k++) {
      swaps[k].p.children.splice(swaps[k].i, 1, swaps[k].m);
      swaps[k].m.parent = swaps[k].p;
    }
    if (swaps.length) root.updateMatrixWorld(true);
    return swaps.length;
  }
"""


def _replace_once(chunk, old, new):
    assert chunk.count(old) == 1, "anchor x%d: %r" % (chunk.count(old), old[:60])
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
                if "Load combined GLB" in text and "Fallback single GLB" in text:
                    yield ev, text
            for r in walk(ev.get("events", [])):
                yield r

    hits = []
    for fn in obj.get("eventsFunctions", []):
        hits.extend(list(walk(fn.get("events", []))))
    assert len(hits) == 1, "expected 1 model chunk, got %d" % len(hits)
    ev, text = hits[0]

    text = _replace_once(
        text,
        "  // ----- Load combined GLB (multi-node) and split per model ref -----",
        BAKE_FN + "  // ----- Load combined GLB (multi-node) and split per model ref -----")
    text = _replace_once(
        text,
        "          var rootClone = gltf.scene.clone(true);",
        "          var rootClone = gltf.scene.clone(true);\n"
        "          apfxBakeSkinned(rootClone); // rigged GLBs pose statically")
    text = _replace_once(
        text,
        "            var nodeName = modelsMeta.map[shapeKey];\n"
        "            var node = rootClone.getObjectByName(nodeName);",
        "            var nodeName = modelsMeta.map[shapeKey];\n"
        "            // Whole-file ref (empty node): private clone of the full scene.\n"
        "            var node = nodeName ? rootClone.getObjectByName(nodeName)\n"
        "              : rootClone.clone(true);")
    text = _replace_once(
        text,
        "              console.warn(\"[AvancedPFX3D] GLB node '\" + nodeName + \"' not found for shape '\" + shapeKey + \"'.\");",
        "              if (nodeName) console.warn(\"[AvancedPFX3D] GLB node '\" + nodeName + \"' not found for shape '\" + shapeKey + \"'.\");")
    text = _replace_once(
        text,
        "          var modelClone = gltf2.scene.clone(true);",
        "          var modelClone = gltf2.scene.clone(true);\n"
        "          apfxBakeSkinned(modelClone); // rigged GLBs pose statically")

    ev["inlineCode"] = text.split("\n")
    with io.open(EXT, "w", encoding="utf-8", newline="") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print("PATCHED-OK")


if __name__ == "__main__":
    main()
