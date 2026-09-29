# Upload chain: dialog payload -> customModel -> form text + status.
# Also covers Wavefront OBJ parsing (v/f, fans, negative indices).
import json
import os
import struct
import tempfile

import bootstrap  # tests/ sys.path setup (repo root + editor/)
import dearpygui.dearpygui as dpg

dpg.create_context()
try:
    import mesh_cache
    import studio_imgui as S

    # 1) OBJ parse
    tmp = tempfile.mkdtemp(prefix="carrot_up_")
    obj = os.path.join(tmp, "box.obj")
    with open(obj, "w") as f:
        f.write("# cube-ish\nv 0 0 0\nv 2 0 0\nv 2 2 0\nv 0 2 0\n"
                "v 0 0 2\njunk line here\n"
                "f 1 2 3 4\n"          # quad -> 2 tris (fan)
                "f -5 -4 -3\n")        # negative indices -> 1 tri
    tris = mesh_cache.load_mesh_tris(obj, "")
    assert tris and len(tris) == 3, tris
    xs = [v[0] for t in tris for v in t]
    assert abs((max(xs) - min(xs)) - 2.0) < 1e-6
    assert mesh_cache.load_mesh_tris(obj + ".missing", "") is None

    # 1b) node names survive a big JSON chunk (> the old 64K peek window):
    # skinned exports (e.g. Godot robot) carry ~300K of JSON.
    import particle_studio as PS
    big = {"asset": {"version": "2.0"},
           "nodes": [{"name": "Alpha", "mesh": 0}, {"name": "Beta"}],
           "meshes": [{"primitives": []}],
           "extras": {"pad": "x" * (100 * 1024)}}
    bjs = json.dumps(big).encode()
    bjs += b" " * ((4 - len(bjs) % 4) % 4)
    assert len(bjs) > 64 * 1024, len(bjs)
    bglb = os.path.join(tmp, "bigjson.glb")
    with open(bglb, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(bjs))
                + struct.pack("<II", len(bjs), 0x4E4F534A) + bjs)
    # big JSON chunk parses AND bone-only Beta is excluded from the picker
    assert PS.model_nodes_from_file(bglb) == ["Alpha"], \
        PS.model_nodes_from_file(bglb)
    assert PS.model_nodes_from_file(obj) == []

    # 2) upload chain via the native picker (monkeypatched path)
    S.build_ui()
    S.APP.sync_all()
    app = S.APP
    S.set_type("3d", commit=False)
    app.sel_state = 0
    st = app.states[0]
    st["shape"] = "custom"
    st.pop("customModel", None)
    st.pop("modelRefs", None)
    app.sync_state_form()
    assert dpg.get_value("custom_file_text") == "no file"

    real_pick = S._native_pick
    S._native_pick = lambda kind: (obj, "")
    try:
        S.upload_custom_model()
    finally:
        S._native_pick = real_pick
    cm = st.get("customModel")
    assert cm and cm.get("file") == "box.obj", cm
    assert cm.get("path") == obj, cm
    assert st.get("modelRefs") == ["box"], st.get("modelRefs")
    assert dpg.get_value("custom_file_text") == "box.obj"
    assert "box.obj" in dpg.get_value("status_text"), \
        dpg.get_value("status_text")
    # mesh resolves for the viewport
    assert S.custom_mesh_tris() is not None

    # 2b) bone-only node falls back to whole file with a warning
    vbin = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    vbin += struct.pack("<3H", 0, 1, 2)
    vdoc = {"asset": {"version": "2.0"},
            "nodes": [{"name": "Meshy", "mesh": 0}, {"name": "Bony"}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0},
                                        "indices": 1, "mode": 4}]}],
            "accessors": [
                {"bufferView": 0, "componentType": 5126, "count": 3,
                 "type": "VEC3"},
                {"bufferView": 1, "componentType": 5123, "count": 3,
                 "type": "SCALAR"}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 6}],
            "buffers": [{"byteLength": 42}]}
    vjs = json.dumps(vdoc).encode()
    vjs += b" " * ((4 - len(vjs) % 4) % 4)
    vglb = os.path.join(tmp, "parts.glb")
    with open(vglb, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(vjs) + 8
                                      + len(vbin))
                + struct.pack("<II", len(vjs), 0x4E4F534A) + vjs
                + struct.pack("<II", len(vbin), 0x004E4942) + vbin)
    assert PS.model_nodes_from_file(vglb) == ["Meshy"]
    st["customModel"] = {"file": "parts.glb", "path": vglb, "node": "Bony",
                         "kind": "model", "nodes": ["Meshy", "Bony"]}
    st["modelRefs"] = ["Bony"]
    assert S._validate_custom_node(st) is False
    assert st["customModel"]["node"] == ""
    assert st.get("modelRefs") == ["parts"], st.get("modelRefs")
    assert "no mesh" in dpg.get_value("status_text"), \
        dpg.get_value("status_text")
    st["customModel"]["node"] = "Meshy"
    assert S._validate_custom_node(st) is True
    assert st["customModel"]["node"] == "Meshy"

    # 3) picker cancel: no crash, no state change, status untouched
    before = dict(st.get("customModel"))
    status_before = dpg.get_value("status_text")
    S._native_pick = lambda kind: ("", "")
    try:
        S.upload_custom_model()
    finally:
        S._native_pick = real_pick
    assert st.get("customModel") == before
    assert dpg.get_value("status_text") == status_before

    # 3b) picker failure: visible error, no state change
    S._native_pick = lambda kind: ("", "boom")
    try:
        S.upload_custom_model()
    finally:
        S._native_pick = real_pick
    assert st.get("customModel") == before
    assert dpg.get_value("msg_text") == "boom", \
        dpg.get_value("msg_text")
    dpg.configure_item("msg_win", show=False)

    # 4) dialog_pick accepts every known payload shape
    P = S.dialog_pick
    assert P({"selections": {"a.glb": "/x/a.glb"}}) == "/x/a.glb"
    assert P({"selections": ["/y/b.glb"]}) == "/y/b.glb"
    assert P({"file_path_name": "/z/c.glb"}) == "/z/c.glb"
    assert P({"file_path": "/z/c.glb"}) == "/z/c.glb"
    assert P({"file_name": "d.glb",
              "current_path": "/w"}) == os.path.join("/w", "d.glb")
    assert P({}) == ""
    assert P(None) == ""
    assert P("junk") == ""

    # 5) Cancel handler: never touches state or status
    st_before = dict(st.get("customModel"))
    status_before = dpg.get_value("status_text")
    S._dialog_cancelled("dlg_model", {})
    S._dialog_cancelled()
    assert st.get("customModel") == st_before
    assert dpg.get_value("status_text") == status_before
    print("UPLOAD-OK")
finally:
    dpg.destroy_context()
