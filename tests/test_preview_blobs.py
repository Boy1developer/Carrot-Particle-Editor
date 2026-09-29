# Preview model blobs: states -> {ref: {mime, file, data64}} embed map.
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "editor"))
import particle_studio as PS

tmp = tempfile.mkdtemp(prefix="carrot_blob_")
glb = os.path.join(tmp, "coin.glb")
payload = b"glTF-BYTES-1234"
with open(glb, "wb") as f:
    f.write(payload)
big = os.path.join(tmp, "huge.glb")
with open(big, "wb") as f:
    f.write(b"x" * (8 * 1024 * 1024 + 1))

states = [
    {"modelRefs": ["coin"],
     "customModel": {"file": "coin.glb", "path": glb, "node": "",
                     "kind": "model", "nodes": []}},
    {"modelRefs": ["ghost"],
     "customModel": {"file": "gone.glb", "path": glb + ".gone", "node": "",
                     "kind": "model", "nodes": []}},
    {"modelRefs": ["big"],
     "customModel": {"file": "huge.glb", "path": big, "node": "",
                     "kind": "model", "nodes": []}},
    {"appearance": {}},  # no model at all
]
blobs = PS.model_blobs_for_states(states)
assert set(blobs) == {"coin"}, blobs
b = blobs["coin"]
assert b["mime"] == "model/gltf-binary" and b["file"] == "coin.glb"
assert base64.b64decode(b["data"]) == payload

# fingerprint reacts only to model-set changes
fp1 = PS.model_fingerprint(states)
assert PS.model_fingerprint(states) == fp1
assert PS.model_fingerprint([]) != fp1
assert PS.model_fingerprint([]) == ()

# export models block: whole-file -> "" node, named node kept as-is
src = [{"customModel": {"file": "r.glb", "node": "", "kind": "model",
                        "nodes": ["A"]}}]
out = [{"modelRefs": ["r"]}]
assert PS.effect_models_block(src, out) == {
    "file": "r.glb", "nodes": ["A"], "map": {"r": ""}}, \
    PS.effect_models_block(src, out)
src[0]["customModel"]["node"] = "A"
out[0]["modelRefs"] = ["A"]
assert PS.effect_models_block(src, out)["map"] == {"A": "A"}
assert PS.effect_models_block([{}], [{}]) is None
print("BLOBS-OK")
